"""
Private access for guided creation. The allowlist gate runs before FSM, routers and providers, so none of
the creation states, buttons, texts or voice messages can be driven by anyone who is not on it - and the
spies on every paid entry point (reading a description, proposing an inscription, generating) prove it.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
from aiogram.fsm.state import State

from handlers.states import CreationStates as S
from services.storage import get_storage
from tests.creation_harness import AUTH, CreationDriver, cr, make_driver  # noqa: F401
from tests.test_access_control import (  # noqa: F401
    ADMIN,
    STRANGER,
    UNAUTHORIZED,
    assert_denied_callback,
    assert_denied_message,
    h,
    make_harness,
)
from utils import creation_ui as ui
from utils.creative_brief import CreativeBrief
from utils.i18n import t


def seeded_brief() -> dict[str, Any]:
    brief = CreativeBrief(lang="ru", flow="free", concept="пионы в вазе", recipient="маме")
    brief.set_inscription("Мама, привет!", source="user")
    return brief.to_dict()


def seed(state: Optional[State]) -> dict[str, Any]:
    return {
        "brief": seeded_brief(),
        "after": "confirm",
        "input_field": "inscription",
        "clarify_kind": "inscription",
        "optional_asked": 0,
        "pending_voice": "закат",
    }


def paid(cr: CreationDriver) -> list[str]:
    spies = cr.spies
    called = [name for name in ("extract", "suggest", "generate", "stt") if getattr(spies, name).called]
    return called + cr.h.paid_calls()


_CREATION_STATES = list(S.__all_states__)


@UNAUTHORIZED
@pytest.mark.parametrize("state", _CREATION_STATES, ids=lambda s: s.state)
async def test_unauthorized_text_in_any_creation_state_is_inert(make_driver, uid: int, state: State) -> None:
    cr = make_driver()
    await cr.h.seed_fsm(uid, state, **seed(state))
    before_db, before_fsm = cr.h.db(), await cr.h.fsm(uid)

    await cr.h.text(uid, "Привет, нарисуй закат")

    assert paid(cr) == []
    assert cr.h.db() == before_db
    assert await cr.h.fsm(uid) == before_fsm
    assert_denied_message(cr.h)


@UNAUTHORIZED
@pytest.mark.parametrize(
    ("state", "data"),
    [
        (S.choosing_mode, ui.CB_MODE + ui.MODE_FREE),
        (S.choosing_mode, ui.CB_MODE + ui.MODE_GUIDED),
        (S.concept, ui.CB_PURPOSE + "birthday"),
        (S.mood, ui.CB_MOOD + "warm"),
        (S.style, ui.CB_STYLE + "style_minimal"),
        (S.inscription, ui.CB_INSCRIPTION + ui.INSC_AI),
        (S.clarifying, ui.CB_INSCRIPTION + ui.INSC_AI),
        (S.reviewing_suggestion, ui.CB_SUGGESTION + ui.SUG_USE),
        (S.reviewing_suggestion, ui.CB_SUGGESTION + ui.SUG_MORE),
        (S.preferences, ui.CB_NEXT),
        (S.caption, ui.CB_CAPTION + "ai"),
        (S.awaiting_text, ui.CB_CLEAR),
        (S.awaiting_text, ui.CB_VOICE_OK),
        (S.confirming, ui.CB_EDIT + ui.FIELD_MOOD),
        (S.confirming, ui.CB_GO),
        (S.confirming, ui.CB_CANCEL),
        (S.generating, ui.CB_GO),
    ],
    ids=lambda v: v.state if isinstance(v, State) else v,
)
async def test_unauthorized_buttons_cannot_drive_creation_or_reach_providers(
    make_driver, uid: int, state: State, data: str
) -> None:
    cr = make_driver()
    await cr.h.seed_fsm(uid, state, **seed(state))
    before_db, before_fsm = cr.h.db(), await cr.h.fsm(uid)

    await cr.h.press(uid, data)

    assert paid(cr) == []
    assert cr.h.db() == before_db
    assert await cr.h.fsm(uid) == before_fsm
    assert_denied_callback(cr.h)
    assert not cr.photos()


@UNAUTHORIZED
async def test_unauthorized_menu_button_cannot_start_creation(make_driver, uid: int) -> None:
    cr = make_driver()
    cr.h.seed_profile(uid)
    before = cr.h.db()

    await cr.h.text(uid, t("btn_create_card", "ru"))

    assert paid(cr) == []
    assert cr.h.db() == before
    assert await cr.h.fsm(uid) == (None, {})
    assert_denied_message(cr.h)


@UNAUTHORIZED
@pytest.mark.parametrize("state", [S.idea, S.concept, S.awaiting_text, S.clarifying], ids=lambda s: s.state)
async def test_unauthorized_voice_in_creation_does_not_reach_speech_recognition(
    make_driver, uid: int, state: State
) -> None:
    cr = make_driver()
    await cr.h.seed_fsm(uid, state, **seed(state))

    await cr.h.voice(uid)

    assert not cr.spies.stt.called
    assert "GetFile" not in cr.h.session.names()
    assert paid(cr) == []
    assert_denied_message(cr.h)


@UNAUTHORIZED
async def test_an_unauthorized_confirmation_cannot_spend_the_daily_cap_or_store_a_card(make_driver, uid: int) -> None:
    cr = make_driver()
    await cr.h.seed_fsm(uid, S.confirming, **seed(S.confirming))

    await cr.h.press(uid, ui.CB_GO)

    assert get_storage().get_daily_count(uid) == 0
    assert get_storage().get_last_card(uid) is None


async def test_an_authorized_user_gets_creation_not_the_denial(cr: CreationDriver) -> None:
    await cr.start()

    assert await cr.state() == S.choosing_mode.state
    assert t("access_denied", "ru") not in cr.all_texts()
    assert ui.MODE_PROMPT in cr.screen()


async def test_an_unconfigured_allowlist_blocks_creation_for_everyone(make_driver) -> None:
    cr = make_driver(ALLOWED_USER_IDS="")

    await cr.start()
    await cr.h.press(AUTH, ui.CB_MODE + ui.MODE_FREE)

    assert cr.h.session.names() == ["SendMessage", "AnswerCallbackQuery"]
    assert cr.h.sent_texts() == [t("access_denied", "ru")]
    assert paid(cr) == []
    cr.h.assert_no_fsm_allocation()


async def test_one_users_confirmation_cannot_be_fired_by_another_user(make_driver) -> None:
    cr = make_driver(ALLOWED_USER_IDS=f"{AUTH},{STRANGER}")
    await cr.h.seed_fsm(AUTH, S.confirming, **seed(S.confirming))

    await cr.h.press(STRANGER, ui.CB_GO)  # allowed, but has no creation of their own

    assert not cr.spies.generate.called
    assert (await cr.h.fsm(AUTH))[0] == S.confirming.state
