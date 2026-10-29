"""
Reading a free-form request into a brief, and proposing an inscription. The text model only proposes: the
guardrails in ``apply_extraction`` decide what the user really said. The provider is always a mock.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.brief_ai import (
    BriefAIError,
    Extraction,
    apply_extraction,
    extract_brief_fields,
    heuristic_extraction,
    parse_extraction,
    suggest_inscription,
)
from services.card_render import check_inscription
from services.providers.openai_text import OpenAITextError
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_NONE,
    CAPTION_UNSPECIFIED,
    CAPTION_USER,
    INSCRIPTION_AI,
    INSCRIPTION_NONE,
    INSCRIPTION_TEXT,
    INSCRIPTION_UNSPECIFIED,
    SOURCE_USER,
    CreativeBrief,
)


def settings(**env: str) -> Settings:
    return Settings(BOT_TOKEN="t", OPENAI_API_KEY="sk-test", **env)


def provider(reply: object) -> MagicMock:
    mock = MagicMock()
    if isinstance(reply, Exception):
        mock.generate_greeting_text = AsyncMock(side_effect=reply)
    else:
        mock.generate_greeting_text = AsyncMock(return_value=reply)
    return mock


def model_json(**fields: object) -> str:
    base: dict[str, object] = {
        "concept": None, "occasion": None, "recipient": None, "mood": None, "style": None,
        "inscription": {"mode": "unspecified", "text": None}, "restrictions": [],
        "caption": {"mode": "unspecified", "text": None}, "signature": None,
        "greeting_card": False, "question": None,
    }
    base.update(fields)
    return json.dumps(base, ensure_ascii=False)


# ---- parsing -------------------------------------------------------------------------------------


def test_parse_extraction_reads_every_field() -> None:
    ex = parse_extraction(
        model_json(
            concept="пионы", occasion="юбилей", recipient="маме", mood="тёплое", style="акварель",
            inscription={"mode": "text", "text": "Привет"}, restrictions=["без людей", " ", 5],
            caption={"mode": "user", "text": "Длинный текст"}, signature="Аня", greeting_card=True,
        )
    )
    assert ex is not None and ex.used_ai
    assert (ex.concept, ex.occasion, ex.recipient, ex.mood, ex.style) == ("пионы", "юбилей", "маме", "тёплое", "акварель")
    assert (ex.inscription_mode, ex.inscription_text) == ("text", "Привет")
    assert ex.restrictions == ["без людей"]
    assert (ex.caption_mode, ex.caption_text, ex.signature, ex.is_card) == ("user", "Длинный текст", "Аня", True)


def test_parse_extraction_tolerates_fences_and_chatter() -> None:
    raw = "Вот результат:\n```json\n" + model_json(concept="лес") + "\n```"
    ex = parse_extraction(raw)
    assert ex is not None and ex.concept == "лес"


@pytest.mark.parametrize("raw", ["", "не json", "[1, 2]", '{"concept": ', "null"])
def test_parse_extraction_rejects_what_is_not_a_json_object(raw: str) -> None:
    assert parse_extraction(raw) is None


def test_parse_extraction_survives_wrong_types() -> None:
    ex = parse_extraction('{"concept": 5, "inscription": "text", "restrictions": "без людей", "caption": 3}')
    assert ex is not None
    assert ex.concept == "" and ex.inscription_mode == INSCRIPTION_UNSPECIFIED and ex.restrictions == []


# ---- guardrails -----------------------------------------------------------------------------------


def merged(source: str, **fields: object) -> CreativeBrief:
    brief = CreativeBrief()
    apply_extraction(brief, Extraction(**fields), source)  # type: ignore[arg-type]
    return brief


def test_an_inscription_found_word_for_word_in_the_message_is_used() -> None:
    brief = merged(
        "Открытка маме, надпись «С днём рождения, мама!»",
        concept="Открытка маме", inscription_mode="text", inscription_text="С днём рождения, мама!",
    )
    assert (brief.inscription_mode, brief.inscription_text, brief.inscription_source) == (
        INSCRIPTION_TEXT, "С днём рождения, мама!", SOURCE_USER,
    )


def test_a_reworded_inscription_is_replaced_by_the_users_marked_quote() -> None:
    brief = merged(
        "Открытка, надпись «С днём рождения, мама!»",
        concept="Открытка", inscription_mode="text", inscription_text="Happy birthday, Mom!",
    )
    assert brief.inscription_text == "С днём рождения, мама!"


def test_a_reworded_inscription_without_a_quote_to_fall_back_on_is_dropped() -> None:
    brief = merged(
        "Открытка маме, на ней пусть будет поздравление с днём рождения",
        concept="Открытка маме", inscription_mode="text", inscription_text="Поздравляю с днём рождения!",
    )
    assert brief.inscription_mode == INSCRIPTION_UNSPECIFIED and brief.inscription_text == ""


def test_the_case_of_the_users_inscription_is_not_changed() -> None:
    brief = merged(
        "надпись «привет, МИР»",
        concept="x", inscription_mode="text", inscription_text="Привет, мир",
    )
    assert brief.inscription_text == "привет, МИР", "a differently-cased copy is not the user's text"


def test_no_text_is_honoured_only_when_the_user_said_so() -> None:
    assert merged("Закат", concept="Закат", inscription_mode="none").inscription_mode == INSCRIPTION_UNSPECIFIED
    assert merged("Закат без надписи", concept="Закат", inscription_mode="none").inscription_mode == INSCRIPTION_NONE
    assert merged("Закат без текста", concept="Закат").inscription_mode == INSCRIPTION_NONE


def test_a_quoted_phrase_is_not_a_no_text_request() -> None:
    brief = merged("Закат, надпись «Жизнь без слов»", concept="Закат", inscription_mode="unspecified")
    assert brief.inscription_mode == INSCRIPTION_TEXT and brief.inscription_text == "Жизнь без слов"


def test_a_marked_quote_the_model_missed_is_still_the_inscription() -> None:
    brief = merged("Лес, надпись «Тишина»", concept="Лес")
    assert (brief.inscription_mode, brief.inscription_text) == (INSCRIPTION_TEXT, "Тишина")


def test_a_model_that_says_none_cannot_be_overridden_by_a_loosely_related_quote() -> None:
    brief = merged("Лес без надписи, как в «Тишине»", concept="Лес", inscription_mode="none")
    assert brief.inscription_mode == INSCRIPTION_NONE


def test_asking_the_ai_for_an_inscription_only_requests_a_suggestion() -> None:
    brief = merged("пионы, придумай надпись", concept="пионы", inscription_mode="ai")
    assert (brief.inscription_mode, brief.inscription_text) == (INSCRIPTION_AI, "")


def test_a_follow_up_adds_to_the_brief_and_does_not_reset_earlier_decisions() -> None:
    brief = CreativeBrief(concept="пионы", recipient="маме")
    brief.set_inscription("Привет", source=SOURCE_USER)
    brief.add_restrictions(["без людей"])

    apply_extraction(brief, Extraction(mood="тёплое"), "тёплое")

    assert brief.mood_text == "тёплое"
    assert (brief.concept, brief.recipient, brief.inscription_text, brief.restrictions) == (
        "пионы", "маме", "Привет", ["без людей"],
    )


def test_restrictions_accumulate_across_messages_without_duplicates() -> None:
    brief = CreativeBrief(concept="x")
    apply_extraction(brief, Extraction(restrictions=["без людей"]), "без людей")
    apply_extraction(brief, Extraction(restrictions=["Без людей", "без красного"]), "Без людей, без красного")
    assert brief.restrictions == ["без людей", "без красного"]


def test_a_user_written_message_is_kept_only_if_it_is_theirs_word_for_word() -> None:
    brief = merged(
        "Открытка, под ней текст: Дорогая бабушка, будь здорова!",
        concept="Открытка", caption_mode="user", caption_text="Дорогая бабушка, будь здорова!",
    )
    assert (brief.caption_mode, brief.caption_text) == (CAPTION_USER, "Дорогая бабушка, будь здорова!")

    invented = merged("Открытка", concept="Открытка", caption_mode="user", caption_text="Что-то придуманное")
    assert invented.caption_mode == CAPTION_UNSPECIFIED and invented.caption_text == ""


def test_message_preferences_none_and_ai_come_through() -> None:
    assert merged("Напиши поздравление", concept="x", caption_mode="ai").caption_mode == CAPTION_AI
    assert merged("Без сообщения", concept="x", caption_mode="none").caption_mode == CAPTION_NONE


def test_a_missing_concept_is_taken_from_a_long_enough_message_unless_the_model_asked_a_question() -> None:
    long_message = "Хочу что-нибудь тёплое и уютное для моей любимой мамы на день рождения"
    assert merged(long_message).concept == long_message
    assert merged(long_message, question="Что нарисовать?").concept == ""
    assert merged("Хочу что-нибудь").concept == ""


def test_the_users_own_concept_wording_wins_over_nothing_and_fields_are_trimmed() -> None:
    brief = merged("x", concept="закат", occasion=" юбилей ", is_card=True)
    assert brief.concept == "закат" and brief.is_card is True and brief.occasion == " юбилей "


# ---- fallback without a model ------------------------------------------------------------------------


def test_heuristic_extraction_keeps_the_whole_message_as_the_concept() -> None:
    ex = heuristic_extraction("  Летний луг с васильками, надпись «Лето!», без людей ")
    assert ex.concept.startswith("Летний луг") and not ex.used_ai
    assert (ex.inscription_mode, ex.inscription_text) == ("text", "Лето!")
    assert ex.restrictions == ["без людей"]


async def test_extraction_uses_the_configured_provider_once() -> None:
    mock = provider(model_json(concept="лес"))
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        ex = await extract_brief_fields("лес", settings())

    assert ex.concept == "лес" and ex.used_ai
    mock.generate_greeting_text.assert_awaited_once()
    system, user = mock.generate_greeting_text.await_args.args
    assert user == "лес"
    assert "Never invent an inscription" in system and "JSON" in system


@pytest.mark.parametrize("reply", [OpenAITextError("boom"), RuntimeError("x"), "not json at all"])
async def test_extraction_degrades_to_the_deterministic_reading(reply: object) -> None:
    mock = provider(reply)
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        ex = await extract_brief_fields("Летний луг, надпись «Лето!»", settings())

    assert not ex.used_ai
    assert ex.concept.startswith("Летний луг") and ex.inscription_text == "Лето!"


async def test_extraction_without_a_configured_provider_makes_no_call() -> None:
    mock = provider(model_json(concept="лес"))
    with (
        patch("services.brief_ai.get_text_provider", return_value=mock),
        patch("services.brief_ai.text_provider_configured", return_value=False),
    ):
        ex = await extract_brief_fields("лес", settings())

    assert ex.concept == "лес" and not mock.generate_greeting_text.called


async def test_extraction_input_is_bounded() -> None:
    mock = provider(model_json(concept="x"))
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        await extract_brief_fields("я" * 10_000, settings())

    assert len(mock.generate_greeting_text.await_args.args[1]) == 2000


# ---- inscription suggestions ---------------------------------------------------------------------------


def suggestion_brief() -> CreativeBrief:
    brief = CreativeBrief(concept="пионы в вазе", occasion="день рождения", recipient="маме")
    brief.add_restrictions(["без людей"])
    return brief


async def test_a_suggestion_is_cleaned_for_the_card_font() -> None:
    mock = provider('«Маме — с любовью! 🎂»\nВторая строка')
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        phrase = await suggest_inscription(suggestion_brief(), settings())

    assert phrase == "Маме — с любовью!"


async def test_the_suggestion_prompt_knows_the_idea_the_language_and_earlier_options() -> None:
    brief = suggestion_brief()
    brief.suggestions_shown = ["Первый вариант"]
    mock = provider("Новый вариант")
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        await suggest_inscription(brief, settings())

    system, user = mock.generate_greeting_text.await_args.args
    assert "Russian" in system and "Первый вариант" in system
    assert "пионы в вазе" in user and "день рождения" in user and "маме" in user and "без людей" in user


async def test_english_cards_get_english_suggestions() -> None:
    brief = suggestion_brief()
    brief.lang = "en"
    mock = provider("Happy birthday, Mom!")
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        await suggest_inscription(brief, settings())

    assert "English" in mock.generate_greeting_text.await_args.args[0]


async def test_an_overlong_suggestion_is_shortened_before_the_user_sees_it() -> None:
    mock = provider("тёплые слова для самого дорогого человека " * 6)
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        phrase = await suggest_inscription(suggestion_brief(), settings())

    assert len(phrase) <= 100 and phrase.endswith("…")
    assert check_inscription(phrase).ok, "what the user approves is exactly what can be drawn"


@pytest.mark.parametrize("reply", ["", "   ", "🎂🎂🎂", " \n \n"])
async def test_a_suggestion_that_cannot_be_drawn_is_an_error(reply: str) -> None:
    mock = provider(reply)
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        with pytest.raises(BriefAIError):
            await suggest_inscription(suggestion_brief(), settings())


async def test_a_provider_failure_becomes_a_brief_ai_error() -> None:
    mock = provider(OpenAITextError("boom"))
    with patch("services.brief_ai.get_text_provider", return_value=mock):
        with pytest.raises(BriefAIError):
            await suggest_inscription(suggestion_brief(), settings())


async def test_suggestions_need_a_configured_provider() -> None:
    mock = provider("x")
    with (
        patch("services.brief_ai.get_text_provider", return_value=mock),
        patch("services.brief_ai.text_provider_configured", return_value=False),
    ):
        with pytest.raises(BriefAIError):
            await suggest_inscription(suggestion_brief(), settings())
    assert not mock.generate_greeting_text.called
