"""
Finished-card flow at handler level: image + embedded phrase + expanded caption, text-only changes that
reuse the clean original, legacy cards without one, and overlapping operations. No network, no providers.

``render_card_image`` is replaced by a stand-in that records exactly which original and phrase a sent
photo was made from, so the tests can check that image, phrase and stored context always agree.
"""
from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import BufferedInputFile
from PIL import Image

from handlers import main
from services import card_render
from services.card_generation import CardTexts, GeneratedCard
from services.storage import LastCardContext, get_storage
from utils.i18n import t

UID = 42
OTHER_UID = 43
CLEAN = b"CLEAN-ORIGINAL"


def fake_render(original: bytes, short_text: str) -> tuple[bytes, bool]:
    if not (short_text or "").strip():
        return original, False
    return b"R[" + original + b"|" + short_text.encode() + b"]", True


@pytest.fixture(autouse=True)
def _providers_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("DAILY_GENERATION_LIMIT", "100")  # the sequence tests run more than the default 5


@pytest.fixture(autouse=True)
def _fake_renderer() -> Any:
    render = AsyncMock(side_effect=lambda original, short: fake_render(original, short))
    with patch.object(main, "render_card_image", render):
        yield render


class Chat:
    """Stands in for the message a card is answered on; records every photo and text sent."""

    def __init__(self) -> None:
        self.photos: list[dict[str, Any]] = []
        self.texts: list[str] = []
        self._count = 0
        self.fail_photo: Optional[Exception] = None

    async def answer_photo(self, *, photo: Any, caption: str, parse_mode: Any = None, reply_markup: Any = None):
        if self.fail_photo is not None:
            raise self.fail_photo
        self._count += 1
        self.photos.append({"photo": photo, "caption": caption, "markup": reply_markup})
        return SimpleNamespace(photo=[SimpleNamespace(file_id=f"sent-{self._count}")])

    async def answer(self, text: str = "", **kwargs: Any) -> MagicMock:
        self.texts.append(text)
        status = MagicMock()
        status.edit_text = AsyncMock()
        status.delete = AsyncMock()
        return status

    def photo_payload(self, index: int = -1) -> Any:
        photo = self.photos[index]["photo"]
        return photo.data if isinstance(photo, BufferedInputFile) else photo

    def caption(self, index: int = -1) -> str:
        return self.photos[index]["caption"]


def make_cq(uid: int = UID, *, message_photo: bool = True) -> tuple[MagicMock, Chat]:
    chat = Chat()
    cq = MagicMock()
    cq.from_user.id = uid
    cq.message = MagicMock()
    cq.message.photo = [MagicMock(file_id="message-photo")] if message_photo else []
    cq.message.answer_photo = chat.answer_photo
    cq.message.answer = chat.answer
    cq.answer = AsyncMock()
    return cq, chat


def ctx_for(**overrides: Any) -> LastCardContext:
    values: dict[str, Any] = {
        "occasion": "occasion_loved",
        "image_description": "cake",
        "holiday": "день рождения",
        "image_style": "style_realistic",
        "text_style": "text_warm",
        "lang": "ru",
        "image_prompt_en": "a cake",
        "photo_file_id": "old-file",
        "caption_html": "old caption",
        "short_text": "old phrase",
    }
    values.update(overrides)
    return LastCardContext(**values)


def seed(uid: int = UID, *, original: Optional[bytes] = CLEAN, **ctx_overrides: Any) -> None:
    get_storage().set_user_lang(uid, "ru")
    get_storage().save_last_card(uid, ctx_for(**ctx_overrides), original=original)


def stored(uid: int = UID) -> tuple[LastCardContext, Optional[bytes]]:
    ctx, original = get_storage().get_last_card_with_original(uid)
    assert ctx is not None
    return ctx, original


def assert_last_photo_matches_store(chat: Chat, uid: int = UID) -> None:
    """The invariant: the photo last sent is made from the stored original and the stored phrase."""
    ctx, original = stored(uid)
    assert original is not None
    assert chat.photo_payload() == fake_render(original, ctx.short_text)[0]
    assert chat.caption() == ctx.caption_html
    assert ctx.photo_file_id == f"sent-{len(chat.photos)}"


def gated(result: Any) -> tuple[Callable[..., Awaitable[Any]], asyncio.Event, asyncio.Event]:
    """A provider stand-in that blocks until released, to hold an operation mid-flight."""
    started, release = asyncio.Event(), asyncio.Event()

    async def run(*args: Any, **kwargs: Any) -> Any:
        started.set()
        await release.wait()
        if isinstance(result, Exception):
            raise result
        return result

    return run, started, release


def wizard_state() -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "occasion": "occasion_loved",
            "image_description": "cake",
            "holiday": "день рождения",
            "image_style": "style_realistic",
            "text_style": "text_warm",
        }
    )
    return state


async def run_wizard(chat: Chat, state: Optional[AsyncMock] = None, *, uid: int = UID, lang: str = "ru") -> AsyncMock:
    state = state or wizard_state()
    anchor = MagicMock()
    anchor.answer = chat.answer
    anchor.answer_photo = chat.answer_photo
    await main._run_card_generation_from_wizard(MagicMock(), anchor, state, uid, lang)  # type: ignore[arg-type]
    return state


def generated(clean: bytes = b"WIZARD-CLEAN", caption: str = "<b>wizard caption</b>", short: str = "Wizard phrase") -> GeneratedCard:
    return GeneratedCard(image_bytes=clean, texts=CardTexts(caption_html=caption, short_text=short), image_prompt_en="wizard prompt")


# =========================================================================
# Delivery of a new card
# =========================================================================


async def test_new_card_has_the_phrase_drawn_on_it_and_the_expanded_caption(_fake_renderer: AsyncMock) -> None:
    chat = Chat()
    with patch.object(main, "run_card_generation", AsyncMock(return_value=generated())):
        await run_wizard(chat)

    assert chat.photo_payload() == b"R[WIZARD-CLEAN|Wizard phrase]"
    assert chat.caption() == "<b>wizard caption</b>"
    _fake_renderer.assert_awaited_once_with(b"WIZARD-CLEAN", "Wizard phrase")


async def test_new_card_saves_the_clean_original_not_the_rendered_image() -> None:
    chat = Chat()
    with patch.object(main, "run_card_generation", AsyncMock(return_value=generated())):
        await run_wizard(chat)

    ctx, original = stored()
    assert original == b"WIZARD-CLEAN"
    assert (ctx.short_text, ctx.caption_html, ctx.image_prompt_en) == (
        "Wizard phrase",
        "<b>wizard caption</b>",
        "wizard prompt",
    )
    assert ctx.photo_file_id == "sent-1"
    assert get_storage().get_daily_count(UID) == 1


async def test_new_card_with_the_real_renderer_sends_a_png_and_keeps_the_exact_original() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), (40, 60, 90)).save(buf, format="PNG")
    clean = buf.getvalue()
    chat = Chat()

    with (
        patch.object(main, "render_card_image", card_render.render_card_image),
        patch.object(main, "run_card_generation", AsyncMock(return_value=generated(clean=clean, short="С днём рождения!"))),
    ):
        await run_wizard(chat)

    sent = chat.photo_payload()
    assert sent != clean
    assert Image.open(io.BytesIO(sent)).size == (512, 512)
    assert stored()[1] == clean


async def test_rendering_failure_still_delivers_the_clean_image_and_the_expanded_caption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(original: bytes, text: str) -> bytes:
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(card_render, "draw_short_text", boom)
    chat = Chat()
    with (
        patch.object(main, "render_card_image", card_render.render_card_image),
        patch.object(main, "run_card_generation", AsyncMock(return_value=generated())),
    ):
        await run_wizard(chat)

    assert chat.photo_payload() == b"WIZARD-CLEAN"
    assert chat.caption() == "<b>wizard caption</b>"
    ctx, original = stored()
    assert original == b"WIZARD-CLEAN"
    assert ctx.short_text == "Wizard phrase"  # kept so a later change can try drawing it again
    assert get_storage().get_daily_count(UID) == 1


async def test_reply_without_a_short_phrase_sends_the_clean_image_with_the_caption() -> None:
    chat = Chat()
    with patch.object(main, "run_card_generation", AsyncMock(return_value=generated(short=""))):
        await run_wizard(chat)

    assert chat.photo_payload() == b"WIZARD-CLEAN"
    assert chat.caption() == "<b>wizard caption</b>"
    assert stored()[0].short_text == ""


# =========================================================================
# Text-only changes reuse the original
# =========================================================================


async def test_new_caption_redraws_on_the_same_original_without_generating_an_image() -> None:
    seed()
    cq, chat = make_cq()
    image = AsyncMock()
    with (
        patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("new caption", "new phrase"))) as text,
        patch.object(main, "run_image_only", image),
        patch.object(main, "run_card_generation", image),
    ):
        await main.regen_text(cq)

    text.assert_awaited_once()
    image.assert_not_called()
    assert chat.photo_payload() == b"R[CLEAN-ORIGINAL|new phrase]"
    assert chat.caption() == "new caption"
    ctx, original = stored()
    assert original == CLEAN
    assert (ctx.short_text, ctx.caption_html, ctx.photo_file_id) == ("new phrase", "new caption", "sent-1")
    assert ctx.lang == "ru"
    assert get_storage().get_daily_count(UID) == 1


async def test_repeated_text_changes_always_start_from_the_clean_original(_fake_renderer: AsyncMock) -> None:
    seed()
    cq, chat = make_cq()
    replies = [CardTexts("c1", "phrase one"), CardTexts("c2", "phrase two"), CardTexts("c3", "phrase three")]
    with patch.object(main, "run_text_only", AsyncMock(side_effect=replies)):
        for _ in replies:
            await main.regen_text(cq)

    assert [call.args[0] for call in _fake_renderer.await_args_list] == [CLEAN, CLEAN, CLEAN]
    assert chat.photo_payload() == b"R[CLEAN-ORIGINAL|phrase three]"
    assert_last_photo_matches_store(chat)


async def test_language_switch_translates_the_phrase_on_the_same_original() -> None:
    seed(lang="ru")
    cq, chat = make_cq()
    image = AsyncMock()
    with (
        patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("english caption", "Happy day"))) as text,
        patch.object(main, "run_image_only", image),
    ):
        await main.regen_card_lang(cq)

    assert text.await_args.kwargs["lang"] == "en"
    image.assert_not_called()
    assert chat.photo_payload() == b"R[CLEAN-ORIGINAL|Happy day]"
    ctx, original = stored()
    assert original == CLEAN
    assert (ctx.lang, ctx.short_text, ctx.caption_html) == ("en", "Happy day", "english caption")
    assert get_storage().get_user_lang(UID) == "ru"  # interface language is untouched


async def test_new_image_carries_the_current_phrase_and_replaces_the_original() -> None:
    seed(short_text="kept phrase", caption_html="kept caption")
    cq, chat = make_cq()
    text = AsyncMock()
    with (
        patch.object(main, "run_image_only", AsyncMock(return_value=(b"NEW-CLEAN", "prompt two"))) as image,
        patch.object(main, "run_text_only", text),
    ):
        await main.regen_image(cq)

    image.assert_awaited_once()
    text.assert_not_called()
    assert chat.photo_payload() == b"R[NEW-CLEAN|kept phrase]"
    assert chat.caption() == "kept caption"
    ctx, original = stored()
    assert original == b"NEW-CLEAN"
    assert (ctx.short_text, ctx.caption_html, ctx.image_prompt_en) == ("kept phrase", "kept caption", "prompt two")
    assert_last_photo_matches_store(chat)


async def test_repeat_resends_the_delivered_card_without_rendering_or_providers(_fake_renderer: AsyncMock) -> None:
    seed(photo_file_id="delivered-file", caption_html="delivered caption")
    cq, chat = make_cq()
    provider = AsyncMock()
    with (
        patch.object(main, "run_text_only", provider),
        patch.object(main, "run_image_only", provider),
    ):
        await main.regen_repeat(cq)

    provider.assert_not_called()
    _fake_renderer.assert_not_called()
    assert chat.photo_payload() == "delivered-file"
    assert chat.caption() == "delivered caption"
    assert stored()[1] == CLEAN


async def test_a_sequence_of_operations_keeps_image_phrase_and_context_in_agreement() -> None:
    chat = Chat()
    with patch.object(main, "run_card_generation", AsyncMock(return_value=generated())):
        await run_wizard(chat)
    assert_last_photo_matches_store(chat)

    cq, cq_chat = make_cq()
    steps: list[tuple[Any, dict[str, Any]]] = [
        (main.regen_text, {"run_text_only": CardTexts("cap A", "phrase A")}),
        (main.regen_card_lang, {"run_text_only": CardTexts("cap B", "phrase B")}),
        (main.regen_image, {"run_image_only": (b"IMG-2", "prompt 2")}),
        (main.regen_text, {"run_text_only": CardTexts("cap C", "phrase C")}),
        (main.regen_image, {"run_image_only": (b"IMG-3", "prompt 3")}),
        (main.regen_card_lang, {"run_text_only": CardTexts("cap D", "phrase D")}),
    ]
    for handler, replies in steps:
        with (
            patch.object(main, "run_text_only", AsyncMock(return_value=replies.get("run_text_only"))),
            patch.object(main, "run_image_only", AsyncMock(return_value=replies.get("run_image_only"))),
        ):
            await handler(cq)
        assert_last_photo_matches_store(cq_chat)

    ctx, original = stored()
    assert original == b"IMG-3"
    assert (ctx.short_text, ctx.caption_html, ctx.lang) == ("phrase D", "cap D", "ru")


# =========================================================================
# Cards saved before embedded captions (no clean original)
# =========================================================================


async def test_legacy_card_text_change_updates_only_the_caption(_fake_renderer: AsyncMock) -> None:
    seed(original=None, short_text="")
    cq, chat = make_cq()
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("fresh caption", "ignored phrase"))):
        await main.regen_text(cq)

    _fake_renderer.assert_not_called()
    assert chat.photo_payload() == "old-file"  # the existing delivered photo, as before
    assert chat.caption() == "fresh caption"
    ctx, original = stored()
    assert original is None
    assert (ctx.caption_html, ctx.short_text) == ("fresh caption", "")


async def test_legacy_card_language_switch_updates_only_the_caption(_fake_renderer: AsyncMock) -> None:
    seed(original=None, short_text="", lang="ru")
    cq, chat = make_cq()
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("english caption", "ignored"))):
        await main.regen_card_lang(cq)

    _fake_renderer.assert_not_called()
    assert chat.photo_payload() == "old-file"
    ctx, original = stored()
    assert original is None
    assert (ctx.lang, ctx.caption_html, ctx.photo_file_id) == ("en", "english caption", "old-file")


async def test_legacy_card_without_any_image_reference_is_refused_cleanly() -> None:
    seed(original=None, short_text="", photo_file_id="")
    cq, chat = make_cq(message_photo=False)
    text = AsyncMock()
    with patch.object(main, "run_text_only", text):
        await main.regen_text(cq)
        await main.regen_card_lang(cq)

    text.assert_not_called()
    assert chat.photos == []
    assert [c.args[0] for c in cq.answer.await_args_list] == ["No image reference"] * 2


async def test_legacy_card_new_image_works_and_starts_keeping_an_original() -> None:
    seed(original=None, short_text="", caption_html="old caption")
    cq, chat = make_cq()
    with patch.object(main, "run_image_only", AsyncMock(return_value=(b"FIRST-ORIGINAL", "prompt two"))):
        await main.regen_image(cq)

    assert chat.photo_payload() == b"FIRST-ORIGINAL"  # no phrase exists for a legacy card
    assert chat.caption() == "old caption"
    ctx, original = stored()
    assert original == b"FIRST-ORIGINAL"
    assert ctx.short_text == ""


async def test_legacy_card_upgrades_to_an_embedded_phrase_on_the_next_text_change() -> None:
    seed(original=None, short_text="")
    cq, chat = make_cq()
    with patch.object(main, "run_image_only", AsyncMock(return_value=(b"FIRST-ORIGINAL", "prompt two"))):
        await main.regen_image(cq)
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("new caption", "first phrase"))):
        await main.regen_text(cq)

    assert chat.photo_payload() == b"R[FIRST-ORIGINAL|first phrase]"
    assert_last_photo_matches_store(chat)


async def test_legacy_card_repeat_still_works() -> None:
    seed(original=None, short_text="", photo_file_id="legacy-file", caption_html="legacy caption")
    cq, chat = make_cq()
    await main.regen_repeat(cq)
    assert chat.photo_payload() == "legacy-file"
    assert chat.caption() == "legacy caption"


# =========================================================================
# Overlapping operations never mix originals, phrases and context
# =========================================================================


async def _hold(coro: Awaitable[Any], started: asyncio.Event) -> asyncio.Task:
    task = asyncio.create_task(coro)  # type: ignore[arg-type]
    await asyncio.wait_for(started.wait(), 2)
    return task


def _busy_alerts(cq: MagicMock) -> list[Any]:
    return [c for c in cq.answer.await_args_list if c.args and c.args[0] == t("card_busy", "ru")]


async def test_new_caption_is_refused_while_a_new_image_is_running() -> None:
    seed(short_text="phrase", caption_html="caption")
    run_image, started, release = gated((b"NEW-CLEAN", "prompt two"))
    cq_image, chat_image = make_cq()
    cq_text, chat_text = make_cq()
    text = AsyncMock(return_value=CardTexts("other caption", "other phrase"))

    with patch.object(main, "run_image_only", run_image), patch.object(main, "run_text_only", text):
        task = await _hold(main.regen_image(cq_image), started)
        await main.regen_text(cq_text)
        release.set()
        await task

    text.assert_not_called()
    assert len(_busy_alerts(cq_text)) == 1
    assert cq_text.answer.await_args_list[0].kwargs == {"show_alert": True}
    assert chat_text.photos == []
    assert chat_image.photo_payload() == b"R[NEW-CLEAN|phrase]"
    assert_last_photo_matches_store(chat_image)
    ctx, original = stored()
    assert (original, ctx.short_text, ctx.caption_html) == (b"NEW-CLEAN", "phrase", "caption")


async def test_new_image_is_refused_while_a_new_caption_is_running() -> None:
    seed()
    run_text, started, release = gated(CardTexts("fresh caption", "fresh phrase"))
    cq_text, chat_text = make_cq()
    cq_image, chat_image = make_cq()
    image = AsyncMock(return_value=(b"NEW-CLEAN", "prompt two"))

    with patch.object(main, "run_text_only", run_text), patch.object(main, "run_image_only", image):
        task = await _hold(main.regen_text(cq_text), started)
        await main.regen_image(cq_image)
        release.set()
        await task

    image.assert_not_called()
    assert len(_busy_alerts(cq_image)) == 1
    assert chat_image.photos == []
    assert chat_text.photo_payload() == b"R[CLEAN-ORIGINAL|fresh phrase]"
    assert_last_photo_matches_store(chat_text)
    assert stored()[1] == CLEAN


async def test_double_tap_runs_the_text_provider_once() -> None:
    seed()
    run_text, started, release = gated(CardTexts("fresh caption", "fresh phrase"))
    cq_first, chat_first = make_cq()
    cq_second, chat_second = make_cq()
    calls = AsyncMock(side_effect=run_text)

    with patch.object(main, "run_text_only", calls):
        task = await _hold(main.regen_text(cq_first), started)
        await main.regen_text(cq_second)
        release.set()
        await task

    calls.assert_awaited_once()
    assert len(chat_first.photos) == 1 and chat_second.photos == []
    assert len(_busy_alerts(cq_second)) == 1
    assert get_storage().get_daily_count(UID) == 1


async def test_language_switch_is_refused_while_a_new_image_is_running() -> None:
    seed(lang="ru")
    run_image, started, release = gated((b"NEW-CLEAN", "prompt two"))
    cq_image, chat_image = make_cq()
    cq_lang, _ = make_cq()
    text = AsyncMock()

    with patch.object(main, "run_image_only", run_image), patch.object(main, "run_text_only", text):
        task = await _hold(main.regen_image(cq_image), started)
        await main.regen_card_lang(cq_lang)
        release.set()
        await task

    text.assert_not_called()
    assert len(_busy_alerts(cq_lang)) == 1
    ctx, original = stored()
    assert (ctx.lang, original) == ("ru", b"NEW-CLEAN")
    assert_last_photo_matches_store(chat_image)


async def test_a_new_card_is_refused_while_a_regeneration_is_running() -> None:
    seed()
    run_text, started, release = gated(CardTexts("fresh caption", "fresh phrase"))
    cq_text, chat_text = make_cq()
    wizard_chat = Chat()
    wizard_generation = AsyncMock(return_value=generated())

    with patch.object(main, "run_text_only", run_text), patch.object(main, "run_card_generation", wizard_generation):
        task = await _hold(main.regen_text(cq_text), started)
        state = await run_wizard(wizard_chat)
        release.set()
        await task

    wizard_generation.assert_not_called()
    assert wizard_chat.texts == [t("card_busy", "ru")]
    assert wizard_chat.photos == []
    state.set_state.assert_not_called()
    assert_last_photo_matches_store(chat_text)
    assert stored()[1] == CLEAN


async def test_a_regeneration_is_refused_while_a_new_card_is_running_and_cannot_overwrite_it() -> None:
    seed()
    run_card, started, release = gated(generated())
    wizard_chat = Chat()
    cq, regen_chat = make_cq()
    regen_provider = AsyncMock()

    with (
        patch.object(main, "run_card_generation", run_card),
        patch.object(main, "run_text_only", regen_provider),
        patch.object(main, "run_image_only", regen_provider),
    ):
        task = await _hold(run_wizard(wizard_chat), started)
        for handler in (main.regen_text, main.regen_image, main.regen_card_lang):
            await handler(cq)
        release.set()
        await task

    regen_provider.assert_not_called()
    assert regen_chat.photos == []
    assert len(_busy_alerts(cq)) == 3
    ctx, original = stored()
    assert original == b"WIZARD-CLEAN"
    assert (ctx.short_text, ctx.caption_html) == ("Wizard phrase", "<b>wizard caption</b>")
    assert_last_photo_matches_store(wizard_chat)


async def test_the_next_operation_runs_after_the_previous_one_finishes() -> None:
    seed()
    cq, chat = make_cq()
    with patch.object(main, "run_text_only", AsyncMock(side_effect=[CardTexts("a", "pa"), CardTexts("b", "pb")])):
        await main.regen_text(cq)
        await main.regen_text(cq)

    assert len(chat.photos) == 2
    assert _busy_alerts(cq) == []
    assert_last_photo_matches_store(chat)


@pytest.mark.parametrize("fail", ["provider", "unexpected", "send"])
async def test_a_failed_operation_releases_the_card_for_the_next_one(fail: str) -> None:
    seed()
    cq, chat = make_cq()
    if fail == "provider":
        first = AsyncMock(side_effect=main.OpenAITextError("provider down"))
    elif fail == "unexpected":
        first = AsyncMock(side_effect=ZeroDivisionError("bug"))
    else:
        first = AsyncMock(return_value=CardTexts("a", "pa"))
        chat.fail_photo = ConnectionError("telegram down")

    with patch.object(main, "run_text_only", first):
        if fail == "provider":
            await main.regen_text(cq)
        else:
            with pytest.raises((ZeroDivisionError, ConnectionError)):
                await main.regen_text(cq)

    # Nothing from the failed attempt was saved.
    ctx, original = stored()
    assert (ctx.caption_html, ctx.short_text, original) == ("old caption", "old phrase", CLEAN)

    chat.fail_photo = None
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("b", "pb"))):
        await main.regen_text(cq)

    assert _busy_alerts(cq) == []
    assert_last_photo_matches_store(chat)


async def test_one_users_operation_does_not_block_another_user() -> None:
    seed(UID)
    seed(OTHER_UID, short_text="other phrase", caption_html="other caption")
    run_image, started, release = gated((b"NEW-CLEAN", "prompt two"))
    cq_a, chat_a = make_cq(UID)
    cq_b, chat_b = make_cq(OTHER_UID)

    with (
        patch.object(main, "run_image_only", run_image),
        patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("b caption", "b phrase"))),
    ):
        task = await _hold(main.regen_image(cq_a), started)
        await main.regen_text(cq_b)
        release.set()
        await task

    assert _busy_alerts(cq_b) == []
    assert chat_b.photo_payload() == b"R[CLEAN-ORIGINAL|b phrase]"
    assert_last_photo_matches_store(chat_a, UID)
    assert_last_photo_matches_store(chat_b, OTHER_UID)
    assert stored(UID)[1] == b"NEW-CLEAN" and stored(OTHER_UID)[1] == CLEAN


def test_the_busy_notice_exists_in_both_languages() -> None:
    ru, en = t("card_busy", "ru"), t("card_busy", "en")
    assert ru and en and ru != en
