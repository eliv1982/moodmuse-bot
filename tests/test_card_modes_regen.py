"""
Stage 2A behaviour with the new card modes: cards made by guided creation keep the inscription and message
the user fixed through "new caption", the language switch and "new image"; legacy cards behave exactly as
before. Handler-level, no network, no providers.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from handlers import main
from services.card_generation import CardTexts
from services.storage import LastCardContext, get_storage
from tests.test_card_flow import CLEAN, UID, Chat, ctx_for, fake_render, make_cq, stored  # noqa: F401
from utils.i18n import t


@pytest.fixture(autouse=True)
def _providers_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("DAILY_GENERATION_LIMIT", "100")


@pytest.fixture(autouse=True)
def _fake_renderer() -> Any:
    render = AsyncMock(side_effect=lambda original, short, **kwargs: fake_render(original, short))
    with patch.object(main, "render_card_image", render):
        yield render


EXACT = "Маме — с любовью!"


def rendered(original: bytes, text: str) -> bytes:
    """What the stand-in renderer produces for this original and phrase."""
    return fake_render(original, text)[0]


def seed_mode_card(**overrides: Any) -> None:
    values: dict[str, Any] = {
        "short_text": EXACT,
        "caption_html": "old caption",
        "inscription_mode": "text",
        "caption_mode": "ai",
        "creative_context": "CTX: пионы в вазе",
    }
    values.update(overrides)
    get_storage().set_user_lang(UID, "ru")
    get_storage().save_last_card(UID, ctx_for(**values), original=CLEAN)


def callbacks(markup: Any) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ---- the buttons offered ----------------------------------------------------------------------------------


def test_default_keyboard_is_the_stage_2a_keyboard() -> None:
    assert callbacks(main.after_card_keyboard("ru", "ru")) == [
        "regen_repeat", "regen_text", "regen_image", "regen_card_lang",
    ]
    assert callbacks(main.after_card_keyboard("ru", "ru", ctx_for())) == [
        "regen_repeat", "regen_text", "regen_image", "regen_card_lang",
    ]


@pytest.mark.parametrize(
    ("inscription", "caption", "text_buttons"),
    [
        ("text", "ai", True),
        ("none", "ai", True),
        ("ai", "ai", True),
        ("text", "user", False),
        ("text", "none", False),
        ("none", "none", False),
        ("none", "user", False),
    ],
)
def test_text_buttons_appear_only_when_the_model_wrote_something(inscription: str, caption: str, text_buttons: bool) -> None:
    ctx = ctx_for(inscription_mode=inscription, caption_mode=caption)
    expected = ["regen_repeat", "regen_text", "regen_image", "regen_card_lang"] if text_buttons else [
        "regen_repeat", "regen_image",
    ]
    assert callbacks(main.after_card_keyboard("ru", "ru", ctx)) == expected
    assert ctx.has_ai_text() is text_buttons


# ---- new caption ------------------------------------------------------------------------------------------


async def test_new_caption_keeps_an_exact_inscription_and_rewrites_only_the_message() -> None:
    seed_mode_card()
    cq, chat = make_cq()
    image = AsyncMock()
    with (
        patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("new caption", "AI PHRASE"))) as text,
        patch.object(main, "run_image_only", image),
    ):
        await main.regen_text(cq)

    image.assert_not_called()
    kwargs = text.await_args.kwargs
    assert kwargs["caption_only"] is True and kwargs["creative_context"] == "CTX: пионы в вазе"
    assert chat.photo_payload() == rendered(CLEAN, EXACT), "the user's text, never the model's"
    ctx, original = stored()
    assert (ctx.short_text, ctx.caption_html, ctx.inscription_mode, ctx.caption_mode) == (
        EXACT, "new caption", "text", "ai",
    )
    assert original == CLEAN


async def test_new_caption_on_a_no_text_card_draws_nothing() -> None:
    seed_mode_card(short_text="", inscription_mode="none")
    cq, chat = make_cq()
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("new caption", "AI PHRASE"))):
        await main.regen_text(cq)

    assert chat.photo_payload() == CLEAN, "no phrase appears on an image the user wanted without text"
    assert stored()[0].short_text == ""


@pytest.mark.parametrize(
    ("inscription", "caption"),
    [("text", "user"), ("text", "none"), ("none", "none"), ("none", "user")],
)
async def test_nothing_is_rewritten_on_a_card_whose_texts_the_user_fixed(inscription: str, caption: str) -> None:
    seed_mode_card(inscription_mode=inscription, caption_mode=caption)
    before = stored()[0]
    cq, chat = make_cq()
    text = AsyncMock()
    with patch.object(main, "run_text_only", text), patch.object(main, "run_card_generation", text):
        await main.regen_text(cq)
        await main.regen_card_lang(cq)

    text.assert_not_called()
    assert not chat.photos
    assert [c.args[0] for c in cq.answer.await_args_list] == [t("card_text_fixed", "ru")] * 2
    assert stored()[0] == before
    assert get_storage().get_daily_count(UID) == 0


# ---- language switch --------------------------------------------------------------------------------------


async def test_language_switch_rewrites_the_message_but_not_the_inscription() -> None:
    seed_mode_card(lang="ru")
    cq, chat = make_cq()
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("english caption", "AI PHRASE"))) as text:
        await main.regen_card_lang(cq)

    assert text.await_args.kwargs["lang"] == "en"
    assert text.await_args.kwargs["caption_only"] is True
    assert chat.photo_payload() == rendered(CLEAN, EXACT), "an exact inscription is never translated"
    ctx, _ = stored()
    assert (ctx.lang, ctx.caption_html, ctx.short_text) == ("en", "english caption", EXACT)


# ---- new image --------------------------------------------------------------------------------------------


async def test_new_image_keeps_the_exact_inscription_and_the_user_written_message() -> None:
    seed_mode_card(caption_mode="user", caption_html="Мой текст", creative_context="")
    cq, chat = make_cq()
    with patch.object(main, "run_image_only", AsyncMock(return_value=(b"NEW-CLEAN", "prompt two"))):
        await main.regen_image(cq)

    assert chat.photo_payload() == rendered(b"NEW-CLEAN", EXACT)
    assert chat.caption() == "Мой текст"
    ctx, original = stored()
    assert (ctx.short_text, ctx.caption_html, ctx.inscription_mode, ctx.caption_mode) == (
        EXACT, "Мой текст", "text", "user",
    )
    assert original == b"NEW-CLEAN"
    assert callbacks(chat.photos[-1]["markup"]) == ["regen_repeat", "regen_image"]


async def test_new_image_of_a_no_text_card_stays_clean_and_captionless() -> None:
    seed_mode_card(short_text="", inscription_mode="none", caption_mode="none", caption_html="", creative_context="")
    cq, chat = make_cq()
    with patch.object(main, "run_image_only", AsyncMock(return_value=(b"NEW-CLEAN", "prompt two"))):
        await main.regen_image(cq)

    assert chat.photo_payload() == b"NEW-CLEAN"
    assert chat.caption() == ""
    assert stored()[0].image_prompt_en == "prompt two"


# ---- repeat -----------------------------------------------------------------------------------------------


async def test_repeat_works_for_a_card_that_has_no_message() -> None:
    seed_mode_card(short_text="", inscription_mode="none", caption_mode="none", caption_html="", photo_file_id="file-1")
    cq, chat = make_cq()

    await main.regen_repeat(cq)

    assert chat.photo_payload() == "file-1" and chat.caption() is None
    assert callbacks(chat.photos[-1]["markup"]) == ["regen_repeat", "regen_image"]


async def test_repeat_without_any_saved_photo_still_says_so() -> None:
    cq, _ = make_cq()
    await main.regen_repeat(cq)
    cq.answer.assert_awaited_once_with(t("no_saved_card", "ru"), show_alert=True)


# ---- legacy cards -----------------------------------------------------------------------------------------


async def test_a_legacy_card_still_gets_a_new_phrase_and_caption_with_the_old_call() -> None:
    get_storage().set_user_lang(UID, "ru")
    get_storage().save_last_card(UID, ctx_for(), original=CLEAN)
    cq, chat = make_cq()
    with patch.object(main, "run_text_only", AsyncMock(return_value=CardTexts("new caption", "new phrase"))) as text:
        await main.regen_text(cq)

    kwargs = text.await_args.kwargs
    assert "caption_only" not in kwargs and "creative_context" not in kwargs
    assert chat.photo_payload() == b"R[CLEAN-ORIGINAL|new phrase]"
    assert (stored()[0].short_text, stored()[0].caption_html) == ("new phrase", "new caption")


def test_cards_saved_before_the_modes_existed_read_back_as_model_written() -> None:
    legacy = {
        "occasion": "occasion_loved", "image_description": "cake", "holiday": "birthday",
        "image_style": "style_realistic", "text_style": "text_warm", "lang": "ru",
        "image_prompt_en": "a cake", "photo_file_id": "f", "caption_html": "c", "short_text": "phrase",
    }
    ctx = LastCardContext.from_dict(legacy)

    assert ctx is not None
    assert (ctx.inscription_mode, ctx.caption_mode, ctx.creative_context) == ("ai", "ai", "")
    assert ctx.has_ai_text()


@pytest.mark.parametrize("junk", ["", "robot", None, 5, ["ai"]])
def test_unknown_stored_modes_fall_back_to_model_written(junk: Any) -> None:
    ctx = LastCardContext.from_dict(
        {**ctx_for().to_dict(), "inscription_mode": junk, "caption_mode": junk}
    )
    assert ctx is not None and (ctx.inscription_mode, ctx.caption_mode) == ("ai", "ai")


def test_the_modes_survive_a_round_trip_through_the_database() -> None:
    get_storage().save_last_card(
        UID, ctx_for(inscription_mode="text", caption_mode="user", creative_context="idea"), original=CLEAN
    )

    ctx, original = stored()

    assert (ctx.inscription_mode, ctx.caption_mode, ctx.creative_context) == ("text", "user", "idea")
    assert original == CLEAN


def test_old_database_rows_without_the_new_fields_still_load(tmp_path: Any) -> None:
    storage = get_storage()
    payload = ctx_for().to_dict()
    for key in ("inscription_mode", "caption_mode", "creative_context"):
        payload.pop(key)
    with closing(sqlite3.connect(tmp_path / "bot.db")) as conn:
        conn.execute("INSERT OR REPLACE INTO last_card (user_id, payload) VALUES (?, ?)", (UID, json.dumps(payload)))
        conn.commit()

    ctx = storage.get_last_card(UID)

    assert ctx is not None and (ctx.inscription_mode, ctx.caption_mode) == ("ai", "ai")
