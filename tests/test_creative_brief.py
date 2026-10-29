"""
The creative brief: the inscription's four states, defaults that are derived rather than invented, the
follow-up policy and readiness rules. Pure logic, no Telegram, no network.
"""
from __future__ import annotations

import pytest

from utils.brief_text import (
    asks_for_no_text,
    heuristic_restrictions,
    is_verbatim,
    marked_quoted_passage,
    quoted_passages,
)
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_NONE,
    CAPTION_UNSPECIFIED,
    CAPTION_USER,
    FOLLOW_UP_CONCEPT,
    FOLLOW_UP_INSCRIPTION,
    INSCRIPTION_TEXT,
    INSCRIPTION_UNSPECIFIED,
    MAX_RESTRICTIONS,
    PROBLEM_CAPTION_INVALID,
    PROBLEM_CONCEPT_MISSING,
    PROBLEM_INSCRIPTION_INVALID,
    PROBLEM_INSCRIPTION_UNAPPROVED,
    SOURCE_AI_APPROVED,
    SOURCE_USER,
    CreativeBrief,
    creative_context,
    first_problem,
    has_greeting_context,
    inscription_to_draw,
    mood_prompt,
    next_follow_up,
    normalize_inscription,
    resolve_caption_mode,
    text_style_for,
)

LIMIT = 1024


# ---- the inscription's states -----------------------------------------------------------------


def test_a_new_brief_has_no_inscription_decision() -> None:
    brief = CreativeBrief()
    assert brief.inscription_mode == INSCRIPTION_UNSPECIFIED
    assert inscription_to_draw(brief) == ""


def test_unspecified_and_explicit_none_are_different_states() -> None:
    unspecified, none = CreativeBrief(), CreativeBrief()
    none.set_no_inscription()

    assert unspecified.inscription_mode != none.inscription_mode
    assert inscription_to_draw(unspecified) == inscription_to_draw(none) == ""


def test_an_ai_request_alone_never_yields_text_to_draw() -> None:
    brief = CreativeBrief(concept="пионы")
    brief.request_ai_inscription()
    brief.inscription_suggestion = "Предложение"

    assert inscription_to_draw(brief) == ""
    assert first_problem(brief, max_caption_len=LIMIT).code == PROBLEM_INSCRIPTION_UNAPPROVED


def test_approving_a_suggestion_records_where_the_text_came_from() -> None:
    brief = CreativeBrief(concept="пионы")
    brief.request_ai_inscription()
    brief.set_inscription("С днём рождения!", source=SOURCE_AI_APPROVED)

    assert (brief.inscription_mode, brief.inscription_text, brief.inscription_source) == (
        INSCRIPTION_TEXT, "С днём рождения!", SOURCE_AI_APPROVED,
    )
    assert brief.inscription_suggestion == ""
    assert first_problem(brief, max_caption_len=LIMIT) is None


def test_a_user_inscription_is_kept_word_for_word() -> None:
    text = "«Люблю» — навсегда,\nМама!"
    brief = CreativeBrief(concept="x")
    brief.set_inscription(f"  {text}\r\n", source=SOURCE_USER)

    assert brief.inscription_text == text
    assert inscription_to_draw(brief) == text


def test_normalize_inscription_only_touches_line_endings_and_the_edges() -> None:
    assert normalize_inscription("  a\r\nb  c\rd \n") == "a\nb  c\nd"


def test_clearing_the_inscription_returns_to_unspecified() -> None:
    brief = CreativeBrief(concept="x")
    brief.set_inscription("Текст", source=SOURCE_USER)
    brief.clear_inscription()

    assert (brief.inscription_mode, brief.inscription_text, brief.inscription_source) == (
        INSCRIPTION_UNSPECIFIED, "", "",
    )


# ---- optional values --------------------------------------------------------------------------


def test_only_the_concept_is_required() -> None:
    brief = CreativeBrief()
    assert first_problem(brief, max_caption_len=LIMIT).code == PROBLEM_CONCEPT_MISSING

    brief.concept = "закат над морем"
    assert first_problem(brief, max_caption_len=LIMIT) is None


def test_mood_and_style_are_set_delegated_or_left_out_independently() -> None:
    brief = CreativeBrief(concept="x")
    brief.set_mood_preset("warm")
    brief.delegate_style()
    assert (brief.mood_key, brief.mood_ai, brief.style_ai) == ("warm", False, True)

    brief.set_mood_text("грустное")
    brief.set_style_preset("style_minimal")
    assert (brief.mood_key, brief.mood_text, brief.mood_ai) == ("", "грустное", False)
    assert (brief.style_key, brief.style_ai) == ("style_minimal", False)

    brief.delegate_mood()
    assert (brief.mood_key, brief.mood_text, brief.mood_ai) == ("", "", True)
    assert mood_prompt(brief) == ""


def test_mood_prompt_uses_the_preset_wording_or_the_users_own() -> None:
    brief = CreativeBrief()
    brief.set_mood_preset("playful")
    assert mood_prompt(brief) == "playful, humorous, lighthearted"
    assert text_style_for(brief) == "text_humor"

    brief.set_mood_text("тёплое и немного грустное")
    assert mood_prompt(brief) == "тёплое и немного грустное"
    assert text_style_for(brief) == "text_warm"


def test_restrictions_keep_wording_dedupe_and_are_capped() -> None:
    brief = CreativeBrief()
    brief.add_restrictions(["без  людей", "Без людей", "только   тёплые цвета"])
    assert brief.restrictions == ["без  людей", "только   тёплые цвета"]

    brief.add_restrictions([f"ограничение {i}" for i in range(20)])
    assert len(brief.restrictions) == MAX_RESTRICTIONS


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, False),
        ({"is_card": True}, True),
        ({"occasion": "юбилей"}, True),
        ({"recipient": "маме"}, True),
        ({"signature": "Аня"}, True),
        ({"caption_mode": CAPTION_AI}, True),
        ({"caption_mode": CAPTION_NONE}, False),
        ({"mood_key": "warm", "style_key": "style_minimal"}, False),
    ],
)
def test_greeting_context(kwargs: dict, expected: bool) -> None:
    assert has_greeting_context(CreativeBrief(concept="x", **kwargs)) is expected


def test_default_extended_message_is_none_for_greetings_and_pictures() -> None:
    assert resolve_caption_mode(CreativeBrief(concept="x", recipient="маме")) == CAPTION_NONE
    assert resolve_caption_mode(CreativeBrief(concept="x")) == CAPTION_NONE


def test_an_explicit_extended_message_choice_always_wins() -> None:
    greeting = CreativeBrief(concept="x", recipient="маме")
    greeting.set_caption(CAPTION_NONE)
    assert resolve_caption_mode(greeting) == CAPTION_NONE

    picture = CreativeBrief(concept="x")
    picture.set_caption(CAPTION_USER, "  Мой текст ")
    assert (resolve_caption_mode(picture), picture.caption_text) == (CAPTION_USER, "Мой текст")

    picture.set_caption(CAPTION_AI)
    assert (picture.caption_mode, picture.caption_text) == (CAPTION_AI, ""), "a user text is dropped when switching"


def test_user_caption_must_fit_telegram_and_not_be_empty() -> None:
    brief = CreativeBrief(concept="x")
    brief.set_caption(CAPTION_USER, "a" * (LIMIT + 1))
    assert first_problem(brief, max_caption_len=LIMIT).code == PROBLEM_CAPTION_INVALID

    brief.set_caption(CAPTION_USER, "a" * LIMIT)
    assert first_problem(brief, max_caption_len=LIMIT) is None


def test_an_inscription_that_cannot_be_drawn_is_a_blocking_problem() -> None:
    brief = CreativeBrief(concept="x")
    brief.set_inscription("С праздником 🎉", source=SOURCE_USER)

    problem = first_problem(brief, max_caption_len=LIMIT)
    assert (problem.code, problem.detail) == (PROBLEM_INSCRIPTION_INVALID, "unsupported")


def test_creative_context_carries_the_idea_the_restrictions_and_the_inscription() -> None:
    brief = CreativeBrief(concept="пионы в вазе")
    brief.set_mood_preset("tender")
    brief.add_restrictions(["без людей"])
    brief.set_inscription("Для тебя", source=SOURCE_USER)

    context = creative_context(brief)
    assert "пионы в вазе" in context and "tender, romantic, gentle" in context
    assert "без людей" in context and "Для тебя" in context and "do not just repeat" in context


# ---- serialisation ------------------------------------------------------------------------------


def test_round_trip_through_a_dict_is_lossless() -> None:
    brief = CreativeBrief(lang="en", flow="free", concept="c", occasion="o", recipient="r", is_card=True)
    brief.set_mood_text("m")
    brief.set_style_preset("style_botanical")
    brief.set_inscription("Надпись\nвторая", source=SOURCE_AI_APPROVED)
    brief.add_restrictions(["a", "b"])
    brief.set_caption(CAPTION_USER, "msg")
    brief.signature = "s"
    brief.suggestions_shown = ["x", "y"]

    assert CreativeBrief.from_dict(brief.to_dict()) == brief


def test_from_dict_ignores_garbage_instead_of_trusting_it() -> None:
    brief = CreativeBrief.from_dict(
        {
            "concept": 5,
            "inscription_mode": "shout",
            "inscription_source": "robot",
            "caption_mode": "???",
            "lang": "de",
            "restrictions": ["ok", 3, "", None],
            "unknown": "x",
        }
    )
    assert brief.concept == ""
    assert brief.inscription_mode == INSCRIPTION_UNSPECIFIED and brief.inscription_source == ""
    assert brief.caption_mode == CAPTION_UNSPECIFIED and brief.lang == "ru"
    assert brief.restrictions == ["ok"]
    assert CreativeBrief.from_dict(None) == CreativeBrief()


# ---- follow-up policy ---------------------------------------------------------------------------


def test_follow_up_asks_for_the_concept_until_it_exists() -> None:
    assert next_follow_up(CreativeBrief(), optional_asked=0) == FOLLOW_UP_CONCEPT
    assert next_follow_up(CreativeBrief(), optional_asked=5) == FOLLOW_UP_CONCEPT


def test_follow_up_does_not_collect_an_optional_greeting_inscription() -> None:
    greeting = CreativeBrief(concept="пионы", recipient="маме")
    assert next_follow_up(greeting, optional_asked=0) is None
    assert next_follow_up(greeting, optional_asked=1) is None


def test_follow_up_never_asks_when_the_description_is_sufficient() -> None:
    picture = CreativeBrief(concept="закат над морем")
    assert next_follow_up(picture, optional_asked=0) is None

    decided = CreativeBrief(concept="пионы", recipient="маме")
    decided.set_inscription("Привет", source=SOURCE_USER)
    assert next_follow_up(decided, optional_asked=0) is None

    declined = CreativeBrief(concept="пионы", recipient="маме")
    declined.set_no_inscription()
    assert next_follow_up(declined, optional_asked=0) is None


def test_follow_up_never_asks_for_mood_style_or_other_optional_values() -> None:
    brief = CreativeBrief(concept="закат", is_card=False)
    assert brief.mood_key == brief.style_key == brief.occasion == ""
    assert next_follow_up(brief, optional_asked=0) is None


# ---- deterministic reading of the user's wording ----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Закат над морем, без надписи",
        "без текста пожалуйста",
        "Картинка без слов",
        "надпись не нужна",
        "текст не нужен",
        "Не надо никаких надписей",
        "Лес без надписей и без слов",
        "no text on it",
        "without any inscription please",
    ],
)
def test_explicit_no_text_requests_are_recognised(text: str) -> None:
    assert asks_for_no_text(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Закат над морем",
        "Открытка маме, надпись «Жизнь без слов»",
        "с надписью «Без текста никуда»",
        "Нарисуй лес без людей",
        "Деревянная поверхность без текстуры",
        "Оставь место без словаря и без букета",
    ],
)
def test_other_wording_is_not_a_no_text_request(text: str) -> None:
    assert asks_for_no_text(text) is False


def test_quoted_passages_in_all_common_quote_styles() -> None:
    text = 'надпись «Раз», потом “Два”, ещё „Три“ и "Четыре"'
    assert quoted_passages(text) == ["Раз", "Два", "Три", "Четыре"]


def test_a_quoted_passage_is_an_inscription_only_when_the_message_marks_it() -> None:
    assert marked_quoted_passage("Открытка маме, надпись «С днём рождения»") == "С днём рождения"
    assert marked_quoted_passage("На открытке написать «Привет»") == "Привет"
    assert marked_quoted_passage("Открытка в стиле «Ван Гог»") is None
    assert marked_quoted_passage("надпись «Раз» и ещё надпись «Два»") is None, "ambiguous: not guessed"


def test_verbatim_means_word_for_word_with_case_but_whitespace_is_forgiven() -> None:
    source = "Открытка маме, надпись «С днём рождения,   мама!»"
    assert is_verbatim(source, "С днём рождения, мама!")
    assert not is_verbatim(source, "с днём рождения, мама!")
    assert not is_verbatim(source, "С днем рождения, мама!")
    assert not is_verbatim(source, "")


def test_fallback_restrictions_are_clauses_in_the_users_wording() -> None:
    found = heuristic_restrictions("Нарисуй лес без людей, не рисуй собак; никаких красных цветов. Без надписи")
    assert found == ["без людей", "не рисуй собак", "никаких красных цветов"]
