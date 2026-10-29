"""
Creation end to end with the real pipeline and the real Pillow renderer: only the three providers are mocked.
This is the check that the user's exact words travel from the chat to the pixels, and that a picture asked
for without text is delivered without any.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from services import card_render
from services.card_generation import run_brief_generation
from services.storage import get_storage
from tests.creation_harness import AUTH, CLEAN_IMAGE, CreationDriver, cr, make_driver  # noqa: F401
from tests.test_access_control import h, make_harness  # noqa: F401
from utils import creation_ui as ui
from utils.creative_brief import CAPTION_USER
from utils.prompts import NO_TEXT_IN_IMAGE


@pytest.fixture
def real_pipeline(cr: CreationDriver, monkeypatch: pytest.MonkeyPatch):
    text = MagicMock()
    text.enhance_image_prompt = AsyncMock(return_value="a lovely refined prompt")
    text.generate_greeting_text = AsyncMock(return_value="Тёплая подпись под картинкой.")
    image = MagicMock()
    image.generate_image = AsyncMock(return_value=CLEAN_IMAGE)
    drawn: list[str] = []
    real_draw = card_render.draw_short_text

    def spy_draw(original: bytes, phrase: str, *, exact: bool = False) -> bytes:
        drawn.append(phrase)
        return real_draw(original, phrase, exact=exact)

    monkeypatch.setattr("handlers.creation.run_brief_generation", run_brief_generation)
    monkeypatch.setattr("handlers.main.render_card_image", card_render.render_card_image)
    monkeypatch.setattr(card_render, "draw_short_text", spy_draw)
    with (
        patch("services.card_generation.get_text_provider", return_value=text),
        patch("services.card_generation.get_image_provider", return_value=image),
    ):
        yield cr, text, image, drawn


async def test_the_exact_inscription_is_drawn_on_the_image_the_user_receives(real_pipeline) -> None:
    cr, text, image, drawn = real_pipeline
    exact = "Маме — с любовью!\n«Твоя Аня»"
    await cr.to_confirmation_guided(inscription=exact)

    await cr.tap(ui.CB_GO)

    assert drawn == [exact], "the renderer drew precisely what the user wrote, nothing added or removed"
    sent = cr.photos()[-1].photo.data
    assert sent != CLEAN_IMAGE and Image.open(io.BytesIO(sent)).size == (256, 256)
    ctx = get_storage().get_last_card(AUTH)
    assert ctx.short_text == exact
    assert get_storage().get_last_card_with_original(AUTH)[1] == CLEAN_IMAGE, "the clean original is kept"
    assert NO_TEXT_IN_IMAGE in image.generate_image.await_args.args[0]


async def test_a_picture_asked_for_without_text_arrives_untouched_and_without_a_message(real_pipeline) -> None:
    cr, text, image, drawn = real_pipeline
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("Нарисуй закат над морем в акварели, без надписи")
    assert "без надписи — по вашему выбору" in cr.screen()
    await cr.tap(ui.CB_GO)

    assert drawn == []
    assert cr.photos()[-1].photo.data == CLEAN_IMAGE
    assert not text.generate_greeting_text.called, "a plain picture gets no generated message either"
    assert cr.photos()[-1].caption in (None, "")
    ctx = get_storage().get_last_card(AUTH)
    assert (ctx.short_text, ctx.inscription_mode, ctx.caption_mode) == ("", "none", "none")
    assert "artwork" in text.enhance_image_prompt.await_args.kwargs and text.enhance_image_prompt.await_args.kwargs["artwork"]


async def test_nothing_is_invented_when_the_inscription_was_never_specified(real_pipeline) -> None:
    cr, text, image, drawn = real_pipeline
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)
    await cr.say("Нарисуй зимний лес")
    assert "не указана" in cr.screen()

    await cr.tap(ui.CB_GO)

    assert drawn == []
    assert cr.photos()[-1].photo.data == CLEAN_IMAGE
    assert get_storage().get_last_card(AUTH).inscription_mode == "none"


async def test_a_user_written_message_and_an_approved_suggestion_reach_the_chat_unchanged(real_pipeline) -> None:
    cr, text, image, drawn = real_pipeline
    cr.spies.suggest.return_value = "Тебе одной"
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "justbecause")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)
    await cr.tap(ui.CB_SUGGESTION + ui.SUG_USE)
    await cr.tap(ui.CB_PREF + ui.FIELD_CAPTION)
    await cr.tap(ui.CB_CAPTION + CAPTION_USER)
    await cr.say("Просто хочу сказать <спасибо> & обнять.")
    await cr.tap(ui.CB_NEXT)
    assert "ваш текст" not in cr.screen().split("Надпись:")[1].split("\n")[0], "the inscription came from the AI"

    await cr.tap(ui.CB_GO)

    assert drawn == ["Тебе одной"]
    assert cr.photos()[-1].caption == "Просто хочу сказать &lt;спасибо&gt; &amp; обнять."
    assert not text.generate_greeting_text.called


async def test_a_brief_with_restrictions_reaches_the_image_provider_in_the_users_words(real_pipeline) -> None:
    cr, text, image, drawn = real_pipeline
    await cr.to_confirmation_guided(inscription=None)
    await cr.tap(ui.CB_EDIT + ui.FIELD_RESTRICTIONS)
    await cr.say("без людей\nтолько тёплые цвета")

    await cr.tap(ui.CB_GO)

    prompt = image.generate_image.await_args.args[0]
    assert "без людей" in prompt and "только тёплые цвета" in prompt
    assert image.generate_image.await_count == 1
