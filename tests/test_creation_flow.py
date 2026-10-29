"""
Guided creation through the production dispatcher: both modes, the shared confirmation screen, editing, back
and cancel, recovery from provider errors. Every paid call is a mock; the image provider is never reached
before the explicit "Создать" press.
"""
from __future__ import annotations

import asyncio
import html
import re

import pytest

from handlers.states import CreationStates as S
from services.brief_ai import Extraction
from services.card_generation import CardTexts, GeneratedCard
from services.providers.openai_image import OpenAIImageError
from services.providers.stt_factory import SpeechToTextError
from services.storage import get_storage
from tests.creation_harness import CLEAN_IMAGE, AUTH, CreationDriver, cr, make_driver, stored_card  # noqa: F401
from tests.test_access_control import h, make_harness  # noqa: F401
from utils import creation_ui as ui
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_NONE,
    CAPTION_USER,
    INSCRIPTION_AI,
    INSCRIPTION_NONE,
    INSCRIPTION_TEXT,
    INSCRIPTION_UNSPECIFIED,
    SOURCE_AI_APPROVED,
    SOURCE_USER,
)
from utils.i18n import t

CONFIRM_TITLE = "Проверьте задумку"


async def new_screens(cr: CreationDriver, action) -> list[str]:
    """Texts of the screens the bot showed while ``action`` (an awaitable factory) ran."""
    before = len(cr._screens())
    await action()
    return [c.text for c in cr._screens()[before:]]


# =========================================================================
# Entry: two equally accessible modes
# =========================================================================


async def test_create_card_offers_both_modes_as_equal_buttons(cr: CreationDriver) -> None:
    await cr.start()

    assert await cr.state() == S.choosing_mode.state
    assert ui.CB_MODE + ui.MODE_GUIDED in cr.callbacks()
    assert ui.CB_MODE + ui.MODE_FREE in cr.callbacks()
    assert cr.spies.generate.call_count == 0


async def test_a_user_without_a_saved_language_picks_one_and_lands_on_the_mode_choice(make_driver) -> None:
    from handlers.states import CardStates

    cr = make_driver()
    get_storage().reset_user_profile_data(AUTH)  # no saved language any more
    assert get_storage().get_user_lang(AUTH) is None

    await cr.start()
    assert await cr.state() == CardStates.choosing_language.state

    await cr.tap("lang_en")

    assert get_storage().get_user_lang(AUTH) == "en"
    assert await cr.state() == S.choosing_mode.state
    assert (await cr.brief()).lang == "en"


async def test_typing_the_language_instead_of_pressing_the_button_also_reaches_the_mode_choice(make_driver) -> None:
    cr = make_driver()
    get_storage().reset_user_profile_data(AUTH)
    await cr.start()

    await cr.say("русский")

    assert get_storage().get_user_lang(AUTH) == "ru"
    assert await cr.state() == S.choosing_mode.state


async def test_the_old_wizard_is_no_longer_the_way_in(cr: CreationDriver) -> None:
    from handlers.states import CardStates

    await cr.start()
    await cr.h.text(AUTH, "хочу создать открытку")  # a typed create-card intent restarts the same entry

    assert await cr.state() == S.choosing_mode.state
    assert await cr.state() != CardStates.choosing_occasion.state


# =========================================================================
# Mode 1: choose from options
# =========================================================================


async def test_guided_creation_completes_and_generates_once_after_confirmation(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided(inscription="Маме — с любовью!")

    assert await cr.state() == S.confirming.state
    assert CONFIRM_TITLE in cr.screen()
    assert cr.spies.generate.call_count == 0, "nothing is generated before the explicit press"

    await cr.tap(ui.CB_GO)

    cr.spies.generate.assert_awaited_once()
    brief = cr.spies.generate.await_args.args[1]
    assert brief.concept == "Поздравительная открытка с днём рождения"
    assert (brief.mood_key, brief.style_key) == ("warm", "style_watercolor")
    assert (brief.inscription_mode, brief.inscription_text, brief.inscription_source) == (
        INSCRIPTION_TEXT, "Маме — с любовью!", SOURCE_USER,
    )
    assert len(cr.photos()) == 1
    assert await cr.state() is None
    assert get_storage().get_daily_count(AUTH) == 1


async def test_guided_steps_come_in_the_agreed_order_without_repeats(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    seen = [await cr.state()]
    for data in (
        ui.CB_PURPOSE + "birthday",
        ui.CB_MOOD + "warm",
        ui.CB_STYLE + "style_minimal",
        ui.CB_INSCRIPTION + ui.INSC_NONE,
        ui.CB_NEXT,
    ):
        await cr.tap(data)
        seen.append(await cr.state())

    assert seen == [
        S.concept.state, S.mood.state, S.style.state, S.inscription.state, S.preferences.state, S.confirming.state,
    ]
    assert len(set(seen)) == len(seen)


async def test_guided_mood_and_style_can_be_left_to_the_ai(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "newyear")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)
    await cr.tap(ui.CB_NEXT)

    brief = await cr.brief()
    assert (brief.mood_ai, brief.style_ai) == (True, True)
    assert (brief.mood_key, brief.mood_text, brief.style_key, brief.style_text) == ("", "", "", "")
    assert cr.screen().count("на усмотрение ИИ") == 2


async def test_guided_typed_concept_replaces_a_purpose_button(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.say("закат над морем, лодка у берега")

    brief = await cr.brief()
    assert brief.concept == "закат над морем, лодка у берега"
    assert await cr.state() == S.mood.state


async def test_retyping_the_concept_drops_the_occasion_the_purpose_button_added(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    await cr.tap(ui.CB_EDIT + ui.FIELD_CONCEPT)
    await cr.say("тихое озеро на рассвете")

    brief = await cr.brief()
    assert brief.concept == "тихое озеро на рассвете"
    assert (brief.occasion, brief.is_card) == ("", False)


async def test_guided_custom_mood_and_style_keep_the_users_words(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "justbecause")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_CUSTOM)
    await cr.say("тёплое и немного ностальгическое")
    await cr.tap(ui.CB_STYLE + ui.CHOICE_CUSTOM)
    await cr.say("в духе импрессионистов")

    brief = await cr.brief()
    assert brief.mood_text == "тёплое и немного ностальгическое"
    assert brief.style_text == "в духе импрессионистов"
    assert await cr.state() == S.inscription.state


async def test_guided_back_returns_to_the_previous_step_and_keeps_answers(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + "festive")
    assert await cr.state() == S.style.state

    await cr.tap(ui.CB_BACK)
    assert await cr.state() == S.mood.state
    assert (await cr.brief()).mood_key == "festive", "going back must not erase the earlier answer"

    await cr.tap(ui.CB_BACK)
    assert await cr.state() == S.concept.state
    assert (await cr.brief()).concept == "Поздравительная открытка с днём рождения"

    await cr.tap(ui.CB_BACK)
    assert await cr.state() == S.choosing_mode.state


async def test_changing_an_earlier_answer_does_not_ask_the_later_ones_again(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided(style="style_minimal", inscription="Привет!")
    before = await cr.brief()

    await cr.tap(ui.CB_EDIT + ui.FIELD_MOOD)
    await cr.tap(ui.CB_MOOD + "calm")

    after = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert after.mood_key == "calm"
    assert (after.style_key, after.inscription_text, after.concept) == (
        before.style_key, before.inscription_text, before.concept,
    )


async def test_preferences_are_optional_and_can_be_skipped_in_one_tap(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "thanks")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)
    assert await cr.state() == S.preferences.state

    await cr.tap(ui.CB_NEXT)

    brief = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert (brief.recipient, brief.restrictions, brief.signature) == ("", [], "")


# =========================================================================
# Mode 2: my idea
# =========================================================================


COMPLETE = Extraction(
    concept="Открытка маме на день рождения с пионами",
    occasion="день рождения",
    recipient="маме",
    mood="тёплое",
    style="акварель",
    inscription_mode="text",
    inscription_text="Мамочка, с днём рождения!",
    restrictions=["без людей", "только светлые тона"],
    is_card=True,
    used_ai=True,
)
COMPLETE_TEXT = (
    "Открытка маме на день рождения с пионами, тёплая, акварель, надпись «Мамочка, с днём рождения!», "
    "без людей, только светлые тона"
)


async def test_a_complete_description_goes_straight_to_confirmation(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = COMPLETE
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    shown = await new_screens(cr, lambda: cr.say(COMPLETE_TEXT))

    assert len(shown) == 1 and CONFIRM_TITLE in shown[0], "no follow-up question for a sufficient description"
    assert await cr.state() == S.confirming.state
    brief = await cr.brief()
    assert (brief.concept, brief.occasion, brief.recipient) == (COMPLETE.concept, "день рождения", "маме")
    assert brief.inscription_text == "Мамочка, с днём рождения!"
    assert brief.restrictions == ["без людей", "только светлые тона"]
    assert not cr.spies.generate.called
    assert not cr.spies.suggest.called


async def test_free_form_description_is_confirmed_then_generated_with_the_same_brief(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = COMPLETE
    await cr.to_confirmation_free(COMPLETE_TEXT)

    await cr.tap(ui.CB_GO)

    brief = cr.spies.generate.await_args.args[1]
    assert brief.inscription_text == "Мамочка, с днём рождения!"
    assert brief.restrictions == ["без людей", "только светлые тона"]
    assert brief.flow == "free"
    assert len(cr.photos()) == 1


async def test_missing_concept_asks_one_contextual_question_and_merges_the_answer(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(
        style="акварель", question="Что нарисовать?", used_ai=True
    )
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("Хочу что-нибудь в акварели")

    assert await cr.state() == S.clarifying.state
    assert "Что нарисовать?" in cr.screen()
    assert (await cr.brief()).style_text == "акварель"

    cr.spies.extract.return_value = Extraction(concept="пионы в вазе", used_ai=True)
    shown = await new_screens(cr, lambda: cr.say("пионы в вазе"))

    brief = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert len(shown) == 1 and CONFIRM_TITLE in shown[0], "one question, then straight to confirmation"
    assert (brief.concept, brief.style_text) == ("пионы в вазе", "акварель"), "the first message survives"
    assert cr.spies.extract.await_count == 2


async def test_the_concept_question_repeats_until_there_is_a_concept_but_never_blocks_cancel(
    cr: CreationDriver,
) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(question="Что нарисовать?", used_ai=True)
    await cr.to_confirmation_free("ну...")
    await cr.say("не знаю")

    assert await cr.state() == S.clarifying.state
    assert (await cr.brief()).concept == ""

    await cr.tap(ui.CB_CANCEL)
    assert await cr.state() is None


async def test_a_greeting_recipient_survives_the_concept_question_and_then_confirms(
    cr: CreationDriver,
) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(recipient="маме", question="Что нарисовать для мамы?", used_ai=True)
    await cr.to_confirmation_free("Хочу что-нибудь для мамы")
    assert "Что нарисовать для мамы?" in cr.screen()

    cr.spies.extract.return_value = Extraction(concept="пионы в вазе", used_ai=True)
    await cr.say("пионы в вазе")

    brief = await cr.brief()
    assert (brief.concept, brief.recipient) == ("пионы в вазе", "маме")
    assert await cr.state() == S.confirming.state and "не указана — текста на картинке не будет" in cr.screen()


async def test_greeting_without_an_inscription_can_add_it_from_confirmation(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(
        concept="пионы в вазе", recipient="маме", occasion="день рождения", is_card=True, used_ai=True
    )
    await cr.to_confirmation_free("Открытка маме на день рождения: пионы в вазе")

    assert await cr.state() == S.confirming.state
    assert "не указана — текста на картинке не будет" in cr.screen()
    await cr.tap(ui.CB_EDIT + ui.FIELD_INSCRIPTION)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_TEXT)

    await cr.say("Мама, ты лучшая!")

    brief = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert (brief.inscription_mode, brief.inscription_text, brief.inscription_source) == (
        INSCRIPTION_TEXT, "Мама, ты лучшая!", SOURCE_USER,
    )
    assert sum("Нужна ли надпись" in text for text in cr.all_texts()) == 0


async def test_declining_the_inscription_from_confirmation_records_explicit_no_text(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(concept="пионы", recipient="маме", is_card=True, used_ai=True)
    await cr.to_confirmation_free("открытка маме: пионы")

    await cr.tap(ui.CB_EDIT + ui.FIELD_INSCRIPTION)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)

    brief = await cr.brief()
    assert (await cr.state(), brief.inscription_mode) == (S.confirming.state, INSCRIPTION_NONE)
    assert "без надписи — по вашему выбору" in cr.screen()


async def test_a_plain_picture_request_is_not_interrogated_about_text(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(concept="закат над морем", style="акварель", used_ai=True)
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    shown = await new_screens(cr, lambda: cr.say("Нарисуй закат над морем в акварели"))

    brief = await cr.brief()
    assert len(shown) == 1 and CONFIRM_TITLE in shown[0]
    assert brief.inscription_mode == INSCRIPTION_UNSPECIFIED, "silence is not consent to text, nor a refusal of it"
    assert "не указана — текста на картинке не будет" in shown[0]


async def test_an_explicit_no_text_request_is_recorded_as_no_text_not_as_unspecified(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(concept="закат над морем", used_ai=True)  # model missed it
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("Закат над морем, без надписи")

    assert (await cr.brief()).inscription_mode == INSCRIPTION_NONE
    assert "без надписи — по вашему выбору" in cr.screen()


async def test_the_model_cannot_decide_on_its_own_that_no_text_is_wanted(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(
        concept="закат над морем", inscription_mode="none", used_ai=True
    )
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("Закат над морем")

    assert (await cr.brief()).inscription_mode == INSCRIPTION_UNSPECIFIED


async def test_an_inscription_the_model_reworded_is_not_used(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(
        concept="пионы", inscription_mode="text", inscription_text="Happy birthday, Mom", used_ai=True
    )
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("пионы, надпись «С днём рождения, мама»")

    brief = await cr.brief()
    assert brief.inscription_text == "С днём рождения, мама", "the user's own quoted words win over a reworded copy"


async def test_description_without_a_model_still_works_from_its_own_wording(cr: CreationDriver) -> None:
    # The default spy is the deterministic fallback used when the text provider is unavailable.
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("Нарисуй летний луг с васильками, надпись «Лето!», без людей")

    brief = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert brief.concept.startswith("Нарисуй летний луг")
    assert brief.inscription_text == "Лето!"
    assert brief.restrictions == ["без людей"]


async def test_ai_inscription_in_a_description_is_proposed_not_applied(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(
        concept="пионы", recipient="маме", inscription_mode="ai", is_card=True, used_ai=True
    )
    await cr.to_confirmation_free("открытка маме с пионами, придумай надпись")

    assert await cr.state() == S.reviewing_suggestion.state
    assert "С днём рождения!" in cr.screen()
    brief = await cr.brief()
    assert brief.inscription_mode == INSCRIPTION_AI and brief.inscription_text == ""
    assert not cr.spies.generate.called

    await cr.tap(ui.CB_SUGGESTION + ui.SUG_USE)

    brief = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert (brief.inscription_text, brief.inscription_source) == ("С днём рождения!", SOURCE_AI_APPROVED)
    assert "предложено ИИ, вы одобрили" in cr.screen()


async def test_back_from_a_clarifying_question_returns_to_the_description(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = Extraction(question="Что изобразить?", used_ai=True)
    await cr.to_confirmation_free("сделай мне что-нибудь")
    assert await cr.state() == S.clarifying.state

    await cr.tap(ui.CB_BACK)
    assert await cr.state() == S.idea.state

    await cr.tap(ui.CB_BACK)
    assert await cr.state() == S.choosing_mode.state


async def test_small_talk_is_not_taken_for_a_description(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("привет")

    assert await cr.state() == S.idea.state
    assert ui.SMALL_TALK_HINT in cr.all_texts()
    assert not cr.spies.extract.called


async def test_a_description_that_opens_with_a_greeting_is_still_a_description(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.say("Привет! Нарисуй, пожалуйста, зимний лес с оленем")

    assert cr.spies.extract.await_count == 1
    assert await cr.state() == S.confirming.state


# =========================================================================
# Inscriptions: exact text, AI suggestions need approval
# =========================================================================


async def test_a_custom_inscription_reaches_generation_and_the_renderer_unchanged(cr: CreationDriver) -> None:
    exact = "Мама, с 8 Марта!\n«Люблю» — навсегда."
    await cr.to_confirmation_guided(purpose="march8", inscription=exact)

    await cr.tap(ui.CB_GO)

    assert cr.spies.generate.await_args.args[1].inscription_text == exact
    cr.spies.render.assert_awaited_once_with(CLEAN_IMAGE, exact, exact=True)
    ctx = stored_card().ctx
    assert (ctx.short_text, ctx.inscription_mode) == (exact, "text")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("С днём рождения 🎂", "🎂"),
        ("Привет " + "очень " * 40, "слишком длинная"),
        ("Ш" * 110, "не помещается"),
    ],
)
async def test_an_inscription_that_cannot_be_drawn_exactly_is_refused_not_altered(
    cr: CreationDriver, text: str, expected: str
) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_TEXT)

    await cr.say(text)

    assert await cr.state() == S.awaiting_text.state
    assert expected in cr.screen()
    assert (await cr.brief()).inscription_mode == INSCRIPTION_UNSPECIFIED


async def test_an_ai_suggestion_is_only_a_proposal_until_the_user_approves_it(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)

    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)

    brief = await cr.brief()
    assert await cr.state() == S.reviewing_suggestion.state
    assert brief.inscription_suggestion == "С днём рождения!"
    assert (brief.inscription_mode, brief.inscription_text) == (INSCRIPTION_AI, ""), "proposal is not the inscription"
    assert cr.callbacks()[0] == ui.CB_SUGGESTION + ui.SUG_USE

    await cr.tap(ui.CB_SUGGESTION + ui.SUG_USE)

    brief = await cr.brief()
    assert (brief.inscription_mode, brief.inscription_text, brief.inscription_source) == (
        INSCRIPTION_TEXT, "С днём рождения!", SOURCE_AI_APPROVED,
    )
    assert await cr.state() == S.preferences.state


async def test_asking_for_another_suggestion_excludes_the_ones_already_shown(cr: CreationDriver) -> None:
    cr.spies.suggest.side_effect = ["Первый вариант", "Второй вариант"]
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)

    await cr.tap(ui.CB_SUGGESTION + ui.SUG_MORE)

    brief = await cr.brief()
    assert brief.inscription_suggestion == "Второй вариант"
    assert brief.suggestions_shown == ["Первый вариант", "Второй вариант"]
    assert brief.inscription_mode == INSCRIPTION_AI


async def test_suggestions_are_capped(cr: CreationDriver) -> None:
    cr.spies.suggest.side_effect = [f"Вариант {i}" for i in range(20)]
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)
    for _ in range(10):
        await cr.tap(ui.CB_SUGGESTION + ui.SUG_MORE)

    assert cr.spies.suggest.await_count == 5
    assert ui.SUGGESTION_LIMIT in cr.all_texts()


async def test_declining_a_suggestion_for_no_text_or_own_text(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)

    await cr.tap(ui.CB_SUGGESTION + ui.SUG_OWN)
    assert await cr.state() == S.awaiting_text.state
    brief = await cr.brief()
    assert (brief.inscription_mode, brief.inscription_suggestion) == (INSCRIPTION_UNSPECIFIED, "")
    await cr.say("Своя надпись")
    assert (await cr.brief()).inscription_source == SOURCE_USER

    await cr.tap(ui.CB_NEXT)
    await cr.tap(ui.CB_EDIT + ui.FIELD_INSCRIPTION)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)
    await cr.tap(ui.CB_SUGGESTION + ui.SUG_NONE)
    assert (await cr.brief()).inscription_mode == INSCRIPTION_NONE


async def test_a_failed_suggestion_leaves_the_user_a_way_forward(cr: CreationDriver) -> None:
    from services.brief_ai import BriefAIError

    cr.spies.suggest.side_effect = BriefAIError("boom")
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)

    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)

    assert await cr.state() == S.inscription.state
    assert ui.SUGGESTION_FAILED in cr.screen()
    assert (await cr.brief()).inscription_mode == INSCRIPTION_UNSPECIFIED


async def test_an_unapproved_suggestion_cannot_be_generated(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    brief = await cr.brief()
    brief.request_ai_inscription()
    brief.inscription_suggestion = "Не одобрено"
    await cr.h.ctx(AUTH).update_data(brief=brief.to_dict())

    await cr.tap(ui.CB_GO)

    assert not cr.spies.generate.called
    assert await cr.state() == S.reviewing_suggestion.state
    assert (await cr.brief()).inscription_text == ""


async def test_explicit_no_text_skips_the_overlay_and_the_prompt_invites_none(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided(inscription=None)
    await cr.tap(ui.CB_GO)

    brief = cr.spies.generate.await_args.args[1]
    assert brief.inscription_mode == INSCRIPTION_NONE
    cr.spies.render.assert_awaited_once_with(CLEAN_IMAGE, "", exact=True)
    assert cr.photos()[-1].photo.data == CLEAN_IMAGE, "no phrase is drawn on a no-text image"
    ctx = stored_card().ctx
    assert (ctx.short_text, ctx.inscription_mode) == ("", "none")


async def test_a_failed_overlay_tells_the_user_instead_of_silently_dropping_the_text(cr: CreationDriver) -> None:
    cr.spies.render.side_effect = None
    cr.spies.render.return_value = (CLEAN_IMAGE, False)
    await cr.to_confirmation_guided(inscription="Важный текст")

    await cr.tap(ui.CB_GO)

    assert ui.RENDER_FAILED_NOTICE in cr.all_texts()
    assert stored_card().ctx.short_text == "Важный текст", "kept so it can be drawn again"


# =========================================================================
# Optional occasion, recipient, restrictions, extended message, signature
# =========================================================================


async def test_optional_details_are_collected_on_demand_and_shown_before_generation(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.say("букет полевых цветов")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)
    assert await cr.state() == S.preferences.state

    await cr.tap(ui.CB_PREF + ui.FIELD_OCCASION)
    await cr.say("юбилей")
    assert await cr.state() == S.preferences.state
    await cr.tap(ui.CB_PREF + ui.FIELD_RECIPIENT)
    await cr.say("бабушке")
    await cr.tap(ui.CB_PREF + ui.FIELD_RESTRICTIONS)
    await cr.say("без людей\nтолько тёплые цвета")
    await cr.tap(ui.CB_PREF + ui.FIELD_CAPTION)
    await cr.tap(ui.CB_CAPTION + CAPTION_USER)
    await cr.say("Дорогая бабушка, будь здорова!")
    await cr.tap(ui.CB_PREF + ui.FIELD_SIGNATURE)
    await cr.say("Аня")
    await cr.tap(ui.CB_NEXT)

    screen = cr.screen()
    for expected in ("юбилей", "бабушке", "без людей", "только тёплые цвета", "Дорогая бабушка, будь здорова!", "Аня"):
        assert expected in screen
    await cr.tap(ui.CB_GO)
    brief = cr.spies.generate.await_args.args[1]
    assert (brief.occasion, brief.recipient, brief.signature) == ("юбилей", "бабушке", "Аня")
    assert brief.restrictions == ["без людей", "только тёплые цвета"]
    assert (brief.caption_mode, brief.caption_text) == (CAPTION_USER, "Дорогая бабушка, будь здорова!")


async def test_extended_message_defaults_to_none_for_either_kind_of_creation(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()  # a birthday card
    assert "нет (по умолчанию)" in cr.screen()

    await cr.tap(ui.CB_CANCEL)
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.say("закат над морем")
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)
    await cr.tap(ui.CB_NEXT)
    assert "нет (по умолчанию)" in cr.screen()  # a plain picture


async def test_the_extended_message_can_be_switched_to_none_or_ai_explicitly(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()

    await cr.tap(ui.CB_EDIT + ui.FIELD_CAPTION)
    await cr.tap(ui.CB_CAPTION + CAPTION_NONE)
    assert (await cr.brief()).caption_mode == CAPTION_NONE
    assert await cr.state() == S.confirming.state
    assert "нет" in cr.screen() and "(по умолчанию)" not in cr.screen().split("Сообщение под картинкой:")[1].split("\n")[0]

    await cr.tap(ui.CB_EDIT + ui.FIELD_CAPTION)
    await cr.tap(ui.CB_CAPTION + CAPTION_AI)
    assert (await cr.brief()).caption_mode == CAPTION_AI


async def test_optional_values_can_be_removed_again(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    await cr.tap(ui.CB_EDIT + ui.FIELD_RECIPIENT)
    await cr.say("маме")
    assert (await cr.brief()).recipient == "маме"

    await cr.tap(ui.CB_EDIT + ui.FIELD_RECIPIENT)
    assert ui.CB_CLEAR in cr.callbacks()
    await cr.tap(ui.CB_CLEAR)

    assert (await cr.brief()).recipient == ""
    assert await cr.state() == S.confirming.state


async def test_invalid_optional_input_keeps_the_user_on_the_same_prompt(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    await cr.tap(ui.CB_EDIT + ui.FIELD_OCCASION)

    await cr.say("https://example.com")

    assert await cr.state() == S.awaiting_text.state
    assert ui.INVALID_BY_FIELD[ui.FIELD_OCCASION] in cr.all_texts()
    assert (await cr.brief()).occasion == "день рождения", "a rejected edit changes nothing"


# =========================================================================
# Confirmation: edit individual parameters, back, cancel
# =========================================================================


async def test_every_confirmation_field_can_be_edited_without_restarting(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    original = await cr.brief()

    await cr.tap(ui.CB_EDIT + ui.FIELD_CONCEPT)
    await cr.say("осенний парк с жёлтыми листьями")
    await cr.tap(ui.CB_EDIT + ui.FIELD_MOOD)
    await cr.tap(ui.CB_MOOD + "cozy")
    await cr.tap(ui.CB_EDIT + ui.FIELD_STYLE)
    await cr.tap(ui.CB_STYLE + "style_botanical")
    await cr.tap(ui.CB_EDIT + ui.FIELD_INSCRIPTION)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_TEXT)
    await cr.say("Осень")
    await cr.tap(ui.CB_EDIT + ui.FIELD_OCCASION)
    await cr.say("начало осени")
    await cr.tap(ui.CB_EDIT + ui.FIELD_RESTRICTIONS)
    await cr.say("без машин")

    brief = await cr.brief()
    assert await cr.state() == S.confirming.state
    assert brief.concept == "осенний парк с жёлтыми листьями"
    assert (brief.mood_key, brief.style_key, brief.inscription_text) == ("cozy", "style_botanical", "Осень")
    assert (brief.occasion, brief.restrictions) == ("начало осени", ["без машин"])
    assert brief.lang == original.lang and brief.flow == original.flow


async def test_back_out_of_an_edit_leaves_the_brief_untouched(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    before = await cr.brief()

    for edit in (ui.FIELD_CONCEPT, ui.FIELD_MOOD, ui.FIELD_INSCRIPTION, ui.FIELD_CAPTION, ui.FIELD_RESTRICTIONS):
        await cr.tap(ui.CB_EDIT + edit)
        await cr.tap(ui.CB_BACK)
        assert await cr.state() == S.confirming.state

    assert (await cr.brief()) == before


async def test_edits_from_the_confirmation_screen_come_back_to_it(cr: CreationDriver) -> None:
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = COMPLETE
    await cr.to_confirmation_free(COMPLETE_TEXT)

    await cr.tap(ui.CB_EDIT + ui.FIELD_INSCRIPTION)
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)
    await cr.tap(ui.CB_SUGGESTION + ui.SUG_USE)

    assert await cr.state() == S.confirming.state
    assert (await cr.brief()).inscription_source == SOURCE_AI_APPROVED


async def _reach(cr: CreationDriver, stage: str) -> str:
    """Bring the user to ``stage`` and return the FSM state that stage is expected to be in."""
    await cr.start()
    if stage == "mode":
        return S.choosing_mode.state
    if stage in ("idea", "clarify"):
        await cr.tap(ui.CB_MODE + ui.MODE_FREE)
        if stage == "idea":
            return S.idea.state
        cr.spies.extract.side_effect = None
        cr.spies.extract.return_value = Extraction(question="Что изобразить?", used_ai=True)
        await cr.say("что-нибудь")
        return S.clarifying.state
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    if stage == "concept":
        return S.concept.state
    await cr.tap(ui.CB_PURPOSE + "birthday")
    if stage == "mood":
        return S.mood.state
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    if stage == "style":
        return S.style.state
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    if stage == "inscription":
        return S.inscription.state
    if stage == "text":
        await cr.tap(ui.CB_INSCRIPTION + ui.INSC_TEXT)
        return S.awaiting_text.state
    if stage == "suggestion":
        await cr.tap(ui.CB_INSCRIPTION + ui.INSC_AI)
        return S.reviewing_suggestion.state
    await cr.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)
    if stage == "preferences":
        return S.preferences.state
    await cr.tap(ui.CB_NEXT)
    assert stage == "confirm"
    return S.confirming.state


@pytest.mark.parametrize(
    "stage",
    ["mode", "concept", "mood", "style", "inscription", "text", "suggestion", "preferences", "idea", "clarify", "confirm"],
)
async def test_cancel_works_at_every_stage_and_nothing_is_generated(cr: CreationDriver, stage: str) -> None:
    expected = await _reach(cr, stage)
    assert await cr.state() == expected, "the test must really be at the stage it claims"

    await cr.tap(ui.CB_CANCEL)

    assert await cr.state() is None
    assert ui.CANCELLED in cr.all_texts()
    assert not cr.spies.generate.called
    assert get_storage().get_daily_count(AUTH) == 0


@pytest.mark.parametrize("stage", ["concept", "mood", "style", "inscription", "text", "suggestion", "preferences", "clarify"])
async def test_back_works_at_every_stage_and_never_loses_answers(cr: CreationDriver, stage: str) -> None:
    expected = await _reach(cr, stage)
    assert await cr.state() == expected
    before = await cr.brief()

    await cr.tap(ui.CB_BACK)

    after = await cr.brief()
    assert await cr.state() != expected
    assert after.concept == before.concept and after.mood_ai == before.mood_ai and after.style_ai == before.style_ai


async def test_slash_cancel_and_the_menu_button_also_leave_the_flow(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    await cr.say("/cancel")
    assert await cr.state() is None

    await cr.to_confirmation_guided()
    await cr.start()  # the menu button restarts instead of being read as text
    assert await cr.state() == S.choosing_mode.state
    assert not cr.spies.generate.called


async def test_menu_button_during_a_text_step_is_not_taken_as_the_answer(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    assert await cr.state() == S.concept.state

    await cr.start()

    assert (await cr.brief()).concept == ""
    assert await cr.state() == S.choosing_mode.state


async def test_typing_where_buttons_are_expected_shows_the_screen_again(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    assert await cr.state() == S.mood.state

    await cr.say("что-то написал")

    assert await cr.state() == S.mood.state
    assert ui.MOOD_PROMPT in cr.screen()


# =========================================================================
# Generation: gating, errors, concurrency
# =========================================================================


async def test_nothing_is_generated_in_either_mode_until_the_explicit_confirmation(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()
    assert cr.spies.generate.call_count == 0 and not cr.photos()
    await cr.say("давайте пока подумаем")  # chatter at the confirmation screen
    await cr.tap(ui.CB_EDIT + ui.FIELD_MOOD)
    await cr.tap(ui.CB_MOOD + "calm")
    assert cr.spies.generate.call_count == 0 and not cr.photos()

    await cr.tap(ui.CB_CANCEL)
    cr.spies.extract.side_effect = None
    cr.spies.extract.return_value = COMPLETE
    await cr.to_confirmation_free(COMPLETE_TEXT)
    assert cr.spies.generate.call_count == 0 and not cr.photos()

    await cr.tap(ui.CB_GO)
    assert cr.spies.generate.call_count == 1 and len(cr.photos()) == 1


async def test_a_provider_failure_returns_to_confirmation_with_the_brief_intact(cr: CreationDriver) -> None:
    cr.spies.generate.side_effect = OpenAIImageError("boom")
    await cr.to_confirmation_guided(inscription="Не потеряйте меня")
    before = await cr.brief()

    await cr.tap(ui.CB_GO)

    assert await cr.state() == S.confirming.state
    assert CONFIRM_TITLE in cr.screen()
    assert t("err_image", "ru") in cr.all_texts()
    assert await cr.brief() == before
    assert get_storage().get_daily_count(AUTH) == 0
    assert get_storage().get_last_card(AUTH) is None

    cr.spies.generate.side_effect = None
    cr.spies.generate.return_value = GeneratedCard(
        image_bytes=CLEAN_IMAGE, texts=CardTexts("", "Не потеряйте меня"), image_prompt_en="p"
    )
    await cr.tap(ui.CB_GO)
    assert len(cr.photos()) == 1 and get_storage().get_daily_count(AUTH) == 1


@pytest.mark.parametrize(
    ("error", "key"),
    [(asyncio.TimeoutError(), "err_timeout"), (RuntimeError("x"), "err_generic")],
)
async def test_other_failures_are_reported_in_russian_and_recoverable(
    cr: CreationDriver, error: Exception, key: str
) -> None:
    cr.spies.generate.side_effect = error
    await cr.to_confirmation_guided()

    await cr.tap(ui.CB_GO)

    assert t(key, "ru") in cr.all_texts()
    assert await cr.state() == S.confirming.state


async def test_a_delivery_failure_after_generation_also_recovers(cr: CreationDriver) -> None:
    cr.spies.render.side_effect = RuntimeError("telegram hiccup")
    await cr.to_confirmation_guided()

    await cr.tap(ui.CB_GO)

    assert await cr.state() == S.confirming.state
    assert get_storage().get_daily_count(AUTH) == 0


async def test_the_daily_limit_blocks_generation_but_keeps_the_brief(make_driver) -> None:
    cr = make_driver(DAILY_GENERATION_LIMIT="1")
    get_storage().increment_generation(AUTH)
    await cr.to_confirmation_guided()

    await cr.tap(ui.CB_GO)

    assert not cr.spies.generate.called
    assert await cr.state() == S.confirming.state
    assert any(c.text == t("rate_limited", "ru") for c in cr.callback_answers())


async def test_missing_provider_configuration_blocks_generation(make_driver) -> None:
    cr = make_driver(OPENAI_API_KEY="")
    await cr.to_confirmation_guided()

    await cr.tap(ui.CB_GO)

    assert not cr.spies.generate.called
    assert await cr.state() == S.confirming.state


async def test_pressing_create_twice_generates_once(cr: CreationDriver) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(settings, brief, *, profile_prefs=None):
        started.set()
        await release.wait()
        return GeneratedCard(CLEAN_IMAGE, CardTexts("", ""), "p")

    cr.spies.generate.side_effect = slow
    await cr.to_confirmation_guided(inscription=None)

    first = asyncio.create_task(cr.tap(ui.CB_GO))
    await started.wait()
    await cr.tap(ui.CB_GO)  # second press while the first is still running
    release.set()
    await first

    assert cr.spies.generate.await_count == 1
    assert len(cr.photos()) == 1
    assert get_storage().get_daily_count(AUTH) == 1


async def test_text_and_buttons_during_generation_get_a_wait_notice(cr: CreationDriver) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(settings, brief, *, profile_prefs=None):
        started.set()
        await release.wait()
        return GeneratedCard(CLEAN_IMAGE, CardTexts("", ""), "p")

    cr.spies.generate.side_effect = slow
    await cr.to_confirmation_guided(inscription=None)
    task = asyncio.create_task(cr.tap(ui.CB_GO))
    await started.wait()

    await cr.say("ну что там?")
    await cr.tap(ui.CB_CANCEL)
    release.set()
    await task

    assert ui.BUSY_GENERATING in cr.all_texts()
    assert any(c.text == ui.BUSY_GENERATING for c in cr.callback_answers())
    assert len(cr.photos()) == 1, "cancel cannot interrupt a running generation"


# =========================================================================
# Voice
# =========================================================================


async def test_a_voice_description_is_confirmed_before_it_is_used(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.h.voice(AUTH)

    assert "закат над морем" in cr.screen() and "Всё верно" in cr.screen()
    assert not cr.spies.extract.called, "recognised speech is not acted on until confirmed"

    await cr.tap(ui.CB_VOICE_OK)

    cr.spies.extract.assert_awaited_once()
    assert (await cr.brief()).concept == "закат над морем"
    assert await cr.state() == S.confirming.state


async def test_rejecting_a_voice_transcript_returns_to_the_prompt(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)
    await cr.h.voice(AUTH)

    await cr.tap(ui.CB_VOICE_RETRY)

    assert await cr.state() == S.idea.state
    assert not cr.spies.extract.called


async def test_voice_that_cannot_be_recognised_asks_for_text(cr: CreationDriver) -> None:
    cr.spies.stt.side_effect = SpeechToTextError("bad audio", reason="technical")
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.h.voice(AUTH)

    assert ui.VOICE_EMPTY in cr.all_texts()
    assert await cr.state() == S.idea.state


async def test_voice_is_not_available_without_speech_recognition(make_driver) -> None:
    cr = make_driver(OPENAI_API_KEY="", STT_PROVIDER="openai")
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.h.voice(AUTH)

    assert ui.VOICE_UNAVAILABLE in cr.all_texts()
    assert not cr.spies.stt.called


async def test_stickers_where_text_is_expected_get_a_hint(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)

    await cr.h.feed(
        {
            "update_id": 91001,
            "message": {
                "message_id": 91002,
                "date": 1700000000,
                "chat": {"id": AUTH, "type": "private"},
                "from": {"id": AUTH, "is_bot": False, "first_name": "T"},
                "sticker": {
                    "file_id": "s", "file_unique_id": "su", "type": "regular",
                    "width": 1, "height": 1, "is_animated": False, "is_video": False,
                },
            },
        }
    )

    assert ui.TEXT_ONLY in cr.all_texts()
    assert await cr.state() == S.idea.state


# =========================================================================
# Presentation limits and language
# =========================================================================


def test_the_confirmation_screen_fits_a_telegram_message_at_the_maximum_input() -> None:
    from utils.creative_brief import CreativeBrief, MAX_RESTRICTIONS, RESTRICTION_MAX_LEN

    brief = CreativeBrief(concept="Я" * 400, occasion="О" * 80, recipient="К" * 80, signature="П" * 80)
    brief.set_mood_text("М" * 80)
    brief.set_style_text("С" * 80)
    brief.set_inscription("Н" * 100, source=SOURCE_USER)
    brief.add_restrictions([f"{i}" + "Р" * (RESTRICTION_MAX_LEN - 1) for i in range(MAX_RESTRICTIONS)])
    brief.set_caption(CAPTION_USER, "&" * 1024)

    summary = ui.render_summary(brief)

    # Telegram counts characters after parsing: tags are free and "&amp;" is one character.
    parsed = html.unescape(re.sub(r"<[^>]+>", "", summary))
    assert len(parsed) < 4096
    assert "…" in summary, "a long message is previewed, not echoed in full"


async def test_the_finished_cards_buttons_follow_the_profile_language_while_creation_stays_russian(
    cr: CreationDriver,
) -> None:
    get_storage().set_user_lang(AUTH, "en")
    await cr.to_confirmation_guided(inscription="Hello")
    assert "Проверьте задумку" in cr.screen()

    await cr.tap(ui.CB_GO)

    labels = [b.text for row in cr.photos()[-1].reply_markup.inline_keyboard for b in row]
    assert t("regen_repeat", "en") in labels and t("regen_image", "en") in labels
    assert cr.spies.generate.await_args.args[1].lang == "en", "the card itself is written in the saved language"


async def test_editing_a_guided_step_from_the_confirmation_does_not_claim_to_be_a_step(cr: CreationDriver) -> None:
    await cr.to_confirmation_guided()

    await cr.tap(ui.CB_EDIT + ui.FIELD_MOOD)

    assert "Шаг" not in cr.screen() and "Настроение" in cr.screen()
    await cr.tap(ui.CB_BACK)
    await cr.tap(ui.CB_EDIT + ui.FIELD_INSCRIPTION)
    assert "Шаг" not in cr.screen()


async def test_the_guided_steps_do_count_their_position(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_GUIDED)
    await cr.tap(ui.CB_PURPOSE + "birthday")
    assert "Шаг 2 из 5" in cr.screen()
    await cr.tap(ui.CB_MOOD + ui.CHOICE_AI)
    assert "Шаг 3 из 5" in cr.screen()
    await cr.tap(ui.CB_STYLE + ui.CHOICE_AI)
    assert "Шаг 4 из 5" in cr.screen()


async def test_typing_instead_of_confirming_a_transcript_drops_the_transcript(cr: CreationDriver) -> None:
    await cr.start()
    await cr.tap(ui.CB_MODE + ui.MODE_FREE)
    await cr.h.voice(AUTH)
    assert (await cr.fsm())[1].get("pending_voice") == "закат над морем"

    await cr.say("лучше так: зимний лес")

    assert (await cr.fsm())[1].get("pending_voice") is None
    assert (await cr.brief()).concept.startswith("лучше так")
