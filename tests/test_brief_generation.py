"""
The real generation pipeline on a creative brief, with mocked providers. What matters here: the inscription
handed to the renderer is exactly the user's (or approved) text and is never produced by the text model, a
no-text brief carries none, restrictions and the "print no text" rule survive prompt refinement, and the
extended message is generated only when it was chosen.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.card_generation import CardTexts, run_brief_generation, run_text_only
from services.providers.openai_text import OpenAITextError
from utils.creative_brief import CAPTION_AI, CAPTION_NONE, CAPTION_USER, SOURCE_AI_APPROVED, SOURCE_USER, CreativeBrief
from utils.prompts import NO_TEXT_IN_IMAGE, build_brief_image_prompt, hard_constraints_clause

SETTINGS = Settings(BOT_TOKEN="t", OPENAI_API_KEY="sk-test")


def providers(refined: str = "refined prompt", caption: str = "Тёплое поздравление.") -> tuple[MagicMock, MagicMock]:
    text = MagicMock()
    text.enhance_image_prompt = AsyncMock(return_value=refined)
    text.generate_greeting_text = AsyncMock(return_value=caption)
    image = MagicMock()
    image.generate_image = AsyncMock(return_value=b"CLEAN-IMAGE")
    return text, image


async def generate(brief: CreativeBrief, text: MagicMock, image: MagicMock):
    with (
        patch("services.card_generation.get_text_provider", return_value=text),
        patch("services.card_generation.get_image_provider", return_value=image),
    ):
        return await run_brief_generation(SETTINGS, brief)


def card_brief(**kwargs: object) -> CreativeBrief:
    brief = CreativeBrief(concept="пионы в вазе", occasion="день рождения", recipient="маме", **kwargs)  # type: ignore[arg-type]
    brief.set_inscription("Маме — с любовью!", source=SOURCE_USER)
    return brief


# ---- the inscription ---------------------------------------------------------------------------------


async def test_the_users_inscription_is_handed_on_unchanged() -> None:
    text, image = providers()
    exact = "«Люблю» — навсегда,\nМама! 🙂 не эмодзи, а текст & <b>"
    brief = card_brief()
    brief.inscription_text = exact  # exactly as stored, whatever it contains

    card = await generate(brief, text, image)

    assert card.texts.short_text == exact
    assert card.image_bytes == b"CLEAN-IMAGE"


async def test_the_text_model_is_never_asked_for_an_inscription() -> None:
    text, image = providers(caption=json.dumps({"short": "ПОДМЕНА", "full": "Подпись"}, ensure_ascii=False))
    brief = card_brief()
    brief.set_caption(CAPTION_AI)

    card = await generate(brief, text, image)

    assert card.texts.short_text == "Маме — с любовью!", "a phrase the model volunteers never replaces the user's"
    system, user = text.generate_greeting_text.await_args.args
    assert '"short"' not in user and '"short"' not in system, "the caption request does not ask for a phrase"


async def test_an_approved_ai_suggestion_is_handed_on_exactly_like_the_users_own_text() -> None:
    text, image = providers()
    brief = card_brief()
    brief.set_inscription("С днём рождения!", source=SOURCE_AI_APPROVED)

    card = await generate(brief, text, image)

    assert card.texts.short_text == "С днём рождения!"


@pytest.mark.parametrize("state", ["unspecified", "none"])
async def test_no_text_and_unspecified_both_mean_no_phrase_is_drawn(state: str) -> None:
    text, image = providers()
    brief = CreativeBrief(concept="закат над морем")
    if state == "none":
        brief.set_no_inscription()

    card = await generate(brief, text, image)

    assert card.texts.short_text == ""


async def test_an_unapproved_ai_request_yields_no_phrase_even_if_a_suggestion_exists() -> None:
    text, image = providers()
    brief = CreativeBrief(concept="закат")
    brief.request_ai_inscription()
    brief.inscription_suggestion = "Не одобрено"

    card = await generate(brief, text, image)

    assert card.texts.short_text == ""


# ---- the image prompt ----------------------------------------------------------------------------------


async def test_the_image_model_is_told_to_print_no_text_whatever_the_refinement_said() -> None:
    text, image = providers(refined="a lovely peony bouquet")
    brief = card_brief()

    card = await generate(brief, text, image)

    prompt = image.generate_image.await_args.args[0]
    assert prompt == card.image_prompt_en
    assert NO_TEXT_IN_IMAGE in prompt


async def test_restrictions_survive_refinement_in_the_users_own_wording() -> None:
    text, image = providers(refined="a lovely peony bouquet")  # the refiner dropped them
    brief = card_brief()
    brief.add_restrictions(["без людей", "только светлые тона"])

    await generate(brief, text, image)

    prompt = image.generate_image.await_args.args[0]
    assert "без людей" in prompt and "только светлые тона" in prompt
    assert "follow them exactly" in prompt


async def test_restrictions_are_not_duplicated_when_refinement_kept_them() -> None:
    kept = f"a bouquet. {hard_constraints_clause(['без людей'])}. {NO_TEXT_IN_IMAGE}"
    text, image = providers(refined=kept)
    brief = card_brief()
    brief.add_restrictions(["без людей"])

    await generate(brief, text, image)

    assert image.generate_image.await_args.args[0].count("без людей") == 1


async def test_a_failed_refinement_falls_back_to_a_draft_that_already_has_the_rules() -> None:
    text, image = providers()
    text.enhance_image_prompt = AsyncMock(side_effect=OpenAITextError("boom"))
    brief = card_brief()
    brief.add_restrictions(["без людей"])
    brief.set_mood_preset("tender")
    brief.set_style_text("в духе импрессионистов")

    await generate(brief, text, image)

    prompt = image.generate_image.await_args.args[0]
    assert "пионы в вазе" in prompt and "tender, romantic, gentle" in prompt
    assert "в духе импрессионистов" in prompt and "без людей" in prompt
    assert prompt.count(NO_TEXT_IN_IMAGE) == 1


async def test_a_picture_is_refined_as_artwork_and_a_greeting_as_a_card() -> None:
    text, image = providers()
    await generate(CreativeBrief(concept="закат над морем"), text, image)
    assert text.enhance_image_prompt.await_args.kwargs["artwork"] is True

    text, image = providers()
    await generate(card_brief(), text, image)
    assert text.enhance_image_prompt.await_args.kwargs["artwork"] is False


def test_a_picture_prompt_does_not_ask_for_a_greeting_card() -> None:
    prompt = build_brief_image_prompt(concept="закат над морем", greeting_card=False)
    assert "greeting card design" not in prompt and "standalone artwork" in prompt


def test_a_greeting_prompt_includes_the_recipient_only_as_mood_context() -> None:
    prompt = build_brief_image_prompt(concept="пионы", recipient="маме", greeting_card=True)
    assert "greeting card design" in prompt and "маме" in prompt and "for mood only" in prompt


def test_a_style_left_to_the_ai_is_not_replaced_by_a_default() -> None:
    prompt = build_brief_image_prompt(concept="пионы")
    assert "chosen to best suit the idea" in prompt and "photorealistic" not in prompt


def test_preset_style_wording_is_used_for_a_preset_key() -> None:
    prompt = build_brief_image_prompt(concept="пионы", style_key="style_watercolor")
    assert "watercolor" in prompt


async def test_mood_and_style_left_to_the_ai_add_nothing_to_the_draft() -> None:
    text, image = providers()
    text.enhance_image_prompt = AsyncMock(side_effect=OpenAITextError("boom"))
    brief = CreativeBrief(concept="закат")
    brief.delegate_mood()
    brief.delegate_style()

    await generate(brief, text, image)

    prompt = image.generate_image.await_args.args[0]
    assert "mood:" not in prompt


# ---- the extended message --------------------------------------------------------------------------------


async def test_an_ai_message_is_one_plain_text_request_with_the_briefs_context() -> None:
    text, image = providers(caption="Дорогая мама <3 & всё такое")
    brief = card_brief()
    brief.add_restrictions(["без людей"])
    brief.set_caption(CAPTION_AI)

    card = await generate(brief, text, image)

    text.generate_greeting_text.assert_awaited_once()
    system, user = text.generate_greeting_text.await_args.args
    assert "пионы в вазе" in system and "без людей" in system and "Маме — с любовью!" in system
    assert "день рождения" in user
    assert card.texts.caption_html == "Дорогая мама &lt;3 &amp; всё такое", "Telegram HTML is escaped"


async def test_a_message_the_user_wrote_is_sent_as_written_without_a_text_request() -> None:
    text, image = providers()
    brief = card_brief()
    brief.set_caption(CAPTION_USER, "Дорогая мама,\nспасибо <тебе> & всем!")

    card = await generate(brief, text, image)

    assert not text.generate_greeting_text.called
    assert card.texts.caption_html == "Дорогая мама,\nспасибо &lt;тебе&gt; &amp; всем!"


async def test_no_message_means_no_text_request_and_an_empty_caption() -> None:
    text, image = providers()
    brief = card_brief()
    brief.set_caption(CAPTION_NONE)

    card = await generate(brief, text, image)

    assert not text.generate_greeting_text.called
    assert card.texts.caption_html == ""


async def test_an_unspecified_message_is_absent_for_both_kinds_of_brief() -> None:
    text, image = providers()
    await generate(card_brief(), text, image)  # a greeting
    assert not text.generate_greeting_text.called

    text, image = providers()
    await generate(CreativeBrief(concept="закат"), text, image)  # a plain picture
    assert not text.generate_greeting_text.called


async def test_the_image_and_the_message_are_generated_together() -> None:
    text, image = providers()
    brief = card_brief()
    brief.set_caption(CAPTION_AI)

    await generate(brief, text, image)

    image.generate_image.assert_awaited_once()
    text.generate_greeting_text.assert_awaited_once()


# ---- text-only rewrites (new caption / language switch) ---------------------------------------------------------


async def test_caption_only_rewrite_asks_for_plain_text_and_carries_the_context() -> None:
    text, _ = providers(caption="Новый текст")
    with patch("services.card_generation.get_text_provider", return_value=text):
        texts = await run_text_only(
            SETTINGS, occasion="", holiday="юбилей", text_style="text_warm", lang="ru",
            creative_context="CTX-MARKER", caption_only=True,
        )

    system, user = text.generate_greeting_text.await_args.args
    assert "CTX-MARKER" in system and '"short"' not in user
    assert texts == CardTexts(caption_html="Новый текст", short_text="")


async def test_a_legacy_rewrite_is_unchanged() -> None:
    text, _ = providers(caption=json.dumps({"short": "Фраза", "full": "Подпись"}, ensure_ascii=False))
    with patch("services.card_generation.get_text_provider", return_value=text):
        texts = await run_text_only(SETTINGS, occasion="occasion_loved", holiday="юбилей", text_style="text_warm", lang="ru")

    system, user = text.generate_greeting_text.await_args.args
    assert '"short"' in user and "CTX" not in system
    assert texts == CardTexts(caption_html="Подпись", short_text="Фраза")
