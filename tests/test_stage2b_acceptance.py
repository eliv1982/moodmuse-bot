"""Independent acceptance regressions: adversarial extraction/refinement and safe paid-call retry."""
from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image, ImageDraw

from config import Settings
from handlers import main
from handlers.states import CreationStates as S
from services.brief_ai import Extraction, apply_extraction
from services.card_generation import CardTexts, GeneratedCard, run_brief_generation
from services.card_render import check_inscription, draw_short_text
from services.providers.openai_text import OpenAITextError
from tests.creation_harness import AUTH, CLEAN_IMAGE, CreationDriver, cr, make_driver  # noqa: F401
from tests.test_access_control import h, make_harness  # noqa: F401
from utils import creation_ui as ui
from utils.creative_brief import CAPTION_AI, CAPTION_NONE, CreativeBrief, creative_context


@pytest.fixture
def pipeline(monkeypatch):
    text, image = MagicMock(), MagicMock()
    text.enhance_image_prompt = AsyncMock(return_value="Draw people wearing red beside a building.")
    text.generate_greeting_text = AsyncMock(return_value="Message")
    image.generate_image = AsyncMock(return_value=CLEAN_IMAGE)
    monkeypatch.setattr("services.card_generation.get_text_provider", lambda settings: text)
    monkeypatch.setattr("services.card_generation.get_image_provider", lambda settings: image)
    return Settings(BOT_TOKEN="t", OPENAI_API_KEY="fake"), text, image


@pytest.mark.parametrize("extracted", [[], ["можно людей"], ["без людей"], ["no people"]])
async def test_original_hard_constraints_survive_omitted_weakened_or_invented_extraction(pipeline, extracted):
    settings, text, image = pipeline
    source = "Пейзаж. " + "подробности " * 40 + "Без людей вообще, включая силуэты и отражения. Только  синие тона."
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(concept="Пейзаж", restrictions=extracted), source)
    brief = CreativeBrief.from_dict(brief.to_dict())

    card = await run_brief_generation(settings, brief)

    prompt = image.generate_image.await_args.args[0]
    assert source in prompt and source in creative_context(brief)
    assert "takes precedence" in prompt
    assert prompt.index(source) > prompt.index("Draw people")
    assert card.image_prompt_en == prompt
    assert "можно людей" not in brief.restrictions and "no people" not in brief.restrictions


async def test_follow_up_constraints_and_long_restrictions_are_not_limited_by_extracted_fields(pipeline):
    settings, _, image = pipeline
    source = "Лес. " + "; ".join(f"Исключить объект номер {i}" for i in range(12))
    followup = ("Не использовать " + "красные элементы " * 20).strip()
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(concept="Лес"), source)
    apply_extraction(brief, Extraction(), followup)
    await run_brief_generation(settings, brief)
    assert source in image.generate_image.await_args.args[0]
    assert followup in image.generate_image.await_args.args[0]


async def test_guided_concept_constraints_survive_refinement_without_extraction(pipeline):
    settings, _, image = pipeline
    source = "Лес без людей и построек, только синие тона"
    await run_brief_generation(settings, CreativeBrief(concept=source))
    assert source in image.generate_image.await_args.args[0]


@pytest.mark.parametrize("mode", ["ai", "text", "none", "unspecified"])
def test_explicit_no_text_outranks_conflicting_extraction(mode):
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(concept="Лес", inscription_mode=mode, inscription_text="Лес"), "Лес без текста")
    assert brief.inscription_mode == "none" and brief.inscription_text == ""


def test_extracted_inscription_and_user_message_recover_original_whitespace():
    source = "Лес, надпись «Раз  два\nтри». Сообщение: Мама,  спасибо!\nЛюблю тебя."
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(
        concept="Лес", inscription_mode="text", inscription_text="Раз два три",
        caption_mode="user", caption_text="Мама, спасибо! Люблю тебя.",
    ), source)
    assert brief.inscription_text == "Раз  два\nтри"
    assert brief.caption_text == "Мама,  спасибо!\nЛюблю тебя."


def test_ai_cannot_delegate_an_extended_message_on_the_users_behalf():
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(concept="Открытка", is_card=True, caption_mode="ai"), "Открытка маме")
    assert brief.caption_mode == "unspecified"


@pytest.mark.parametrize("source", [
    "Пионы, напиши поздравление маме", "Flowers; write a warm message under the picture",
    "Пионы, сообщение на твой вкус", "Пионы, сообщение доверь ИИ",
])
def test_explicit_message_delegation_is_accepted(source):
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(concept="Пионы", caption_mode="ai"), source)
    assert brief.caption_mode == CAPTION_AI


@pytest.mark.parametrize("source", [
    "Лес, без дополнительного сообщения", "Forest, don't write a message",
    "Лес, надпись придумай, но без сообщения под картинкой",
])
def test_a_declined_message_outranks_ai_extraction(source):
    brief = CreativeBrief(caption_mode=CAPTION_AI)
    apply_extraction(brief, Extraction(concept="Лес", caption_mode="ai"), source)
    assert brief.caption_mode == CAPTION_NONE


def test_extraction_cannot_silently_discard_a_user_written_message():
    brief = CreativeBrief(caption_mode="user", caption_text="Мой текст")
    apply_extraction(brief, Extraction(caption_mode="none"), "Только тёплые тона")
    assert brief.caption_mode == "user" and brief.caption_text == "Мой текст"


def test_a_quoted_extended_message_is_not_mistaken_for_an_image_inscription():
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(concept="Пионы", caption_mode="user", caption_text="Спасибо, мама!"),
                     "Пионы, текст под картинкой: «Спасибо, мама!»")
    assert brief.caption_text == "Спасибо, мама!" and brief.inscription_mode == "unspecified"


async def test_greeting_without_optional_text_goes_straight_to_confirmation(cr: CreationDriver):
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(concept="пионы", recipient="маме", is_card=True)
    await cr.to_confirmation_free("Открытка маме с пионами")
    assert await cr.state() == S.confirming.state
    assert "не указана — текста на картинке не будет" in cr.screen()
    assert "нет (по умолчанию)" in cr.screen()
    assert not cr.spies.generate.called
    await cr.tap(ui.CB_GO)
    assert cr.spies.generate.await_args.args[1].caption_mode == "unspecified"
    assert cr.photos()[-1].caption in ("", None)


async def test_user_can_replace_or_clear_constraints_even_when_extraction_omitted_them(cr: CreationDriver):
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(concept="Лес")
    await cr.to_confirmation_free("Лес, никаких людей")
    assert "сохранены целиком" in cr.screen()
    await cr.tap(ui.CB_EDIT + ui.FIELD_RESTRICTIONS)
    assert ui.CB_CLEAR in cr.callbacks()
    await cr.tap(ui.CB_CLEAR)
    brief = await cr.brief()
    assert brief.restrictions_edited and brief.restrictions == []
    assert "explicitly replaced" in creative_context(brief)


@pytest.mark.parametrize("failed", ["caption", "image"])
async def test_provider_failure_drains_the_sibling_before_retry_is_possible(pipeline, failed):
    settings, text, image = pipeline
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def pending(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def fail(*args, **kwargs):
        await started.wait()
        raise OpenAITextError("failure")

    image.generate_image.side_effect = pending if failed == "caption" else fail
    text.generate_greeting_text.side_effect = fail if failed == "caption" else pending
    brief = CreativeBrief(concept="Лес", caption_mode=CAPTION_AI)
    with pytest.raises(OpenAITextError):
        await run_brief_generation(settings, brief)
    assert cancelled.is_set()


async def test_stale_confirmation_that_finishes_preflight_late_cannot_generate_again(cr: CreationDriver, monkeypatch):
    await cr.to_confirmation_guided(inscription=None)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def preflight(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return None

    monkeypatch.setattr(main, "_generation_preflight_alert", preflight)
    delayed = asyncio.create_task(cr.tap(ui.CB_GO))
    await entered.wait()
    await cr.tap(ui.CB_GO)
    release.set()
    await delayed
    assert cr.spies.generate.await_count == 1


def test_exact_rendering_on_landscape_never_shortens_the_approved_text(monkeypatch):
    phrase = "Первая\nВторая\nТретья\nЧетвёртая\nПятая"
    assert check_inscription(phrase).ok
    original = io.BytesIO()
    Image.new("RGB", (1536, 1024)).save(original, format="PNG")
    rendered = []
    original_draw = ImageDraw.ImageDraw.text

    def spy(draw, xy, text, *args, **kwargs):
        rendered.append(text)
        return original_draw(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    draw_short_text(original.getvalue(), phrase, exact=True)
    assert rendered == phrase.splitlines()


def test_exact_wrap_keeps_multiple_spaces_and_blank_lines():
    from services.card_render import _font, wrap_text
    assert wrap_text("Раз  два\n\nтри", _font(40), 10000, exact=True) == ["Раз  два", "", "три"]


@pytest.mark.parametrize("provider_name", ["openai", "yandex"])
@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("artwork", [None, False, True])
async def test_artwork_flag_is_compatible_with_both_actual_text_adapters(monkeypatch, provider_name, lang, artwork):
    from services.providers.openai_text import OpenAITextProvider
    from services.providers.yandex_text import YandexTextProvider

    settings = Settings(BOT_TOKEN="t", OPENAI_API_KEY="fake", YANDEX_API_KEY="fake", YANDEX_FOLDER_ID="fake")
    completion = AsyncMock(return_value="refined prompt")
    if provider_name == "openai":
        provider = OpenAITextProvider(settings)
        monkeypatch.setattr(provider, "_completion", completion)
    else:
        provider = YandexTextProvider(settings)
        monkeypatch.setattr("services.yandex_gpt.completion", completion)
    options = {} if artwork is None else {"artwork": artwork}
    assert await provider.enhance_image_prompt(draft_english_prompt="draft", lang=lang, timeout=1, **options) == "refined prompt"
    args = completion.await_args.args
    system = args[0] if provider_name == "openai" else args[0][0]["text"]
    assert ("standalone artwork" in system or "самостоятельное изображение" in system) == (artwork is True)


async def test_old_wizard_callbacks_cannot_reenter_generation_from_creation(cr: CreationDriver):
    from utils.field_confirm import TEXT_CONFIRM_OK
    from utils.wizard_personalization import WIZARD_SIGNATURE_NO

    await cr.to_confirmation_guided(inscription=None)
    before = await cr.brief()
    for callback in ("occasion_loved", "style_realistic", "text_warm", WIZARD_SIGNATURE_NO, TEXT_CONFIRM_OK):
        await cr.tap(callback)
        assert await cr.state() == S.confirming.state
        assert await cr.brief() == before
    assert not cr.h.spies.card.called and not cr.spies.generate.called
