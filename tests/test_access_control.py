"""
Private access, end to end: a real Dispatcher with the production middlewares and routers, a fake
Telegram session, and spies on every paid-provider entry point.

Providers are configured (so handlers *would* call them); only the access gate stands in the way.
"""
from __future__ import annotations

import io
import itertools
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock

import aiohttp
import pytest
from PIL import Image
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.dispatcher.middlewares.error import ErrorsMiddleware
from aiogram.dispatcher.middlewares.user_context import UserContextMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.middleware import FSMContextMiddleware
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import Chat, File, Message, PhotoSize, Update

import bot as bot_module
from config import get_settings
from handlers import admin_router, main_router, profile_router
from handlers.middlewares import ACCESS_NOTICE_INTERVAL_SECONDS, AccessMiddleware, MaintenanceMiddleware
from handlers.states import CardStates, ProfileStates
from services.card_generation import CardTexts, GeneratedCard
from services.storage import LastCardContext, get_storage
from utils.i18n import t
from utils.wizard_personalization import WIZARD_SIGNATURE_NO

BOT_ID = 123456
AUTH = 1001  # on the allowlist
STRANGER = 2002  # not on the allowlist
ADMIN = 3003  # listed in ADMIN_USER_IDS, deliberately not on the allowlist

_TABLES = ("user_prefs", "daily_counts", "generation_log", "last_card", "kv")
_CARD_PHOTO = [{"file_id": "card-photo", "file_unique_id": "card-photo-u", "width": 1, "height": 1}]


class FakeSession(BaseSession):
    """Records Telegram API calls; never touches the network."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Any] = []
        self.fail_answer_callback = False
        self._ids = itertools.count(9000)

    async def close(self) -> None:
        return None

    async def make_request(self, bot: Bot, method: Any, timeout: Optional[int] = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__
        if name == "AnswerCallbackQuery" and self.fail_answer_callback:
            raise TelegramBadRequest(method=method, message="query is too old")
        if name == "GetFile":
            return File(file_id="v", file_unique_id="vu", file_path="voice/f.oga")
        if name in ("SendMessage", "EditMessageText", "SendPhoto"):
            kwargs: dict[str, Any] = {}
            if name == "SendPhoto":
                kwargs["photo"] = [
                    PhotoSize(file_id="sent-photo", file_unique_id="sent-photo-u", width=1, height=1)
                ]
            chat_id = getattr(method, "chat_id", None) or 0
            return Message(
                message_id=next(self._ids),
                date=datetime.now(timezone.utc),
                chat=Chat(id=int(chat_id), type="private"),
                **kwargs,
            ).as_(bot)
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        yield b"OggS-fake-audio"

    def names(self) -> list[str]:
        return [type(c).__name__ for c in self.calls]


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (40, 60, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _user(uid: int) -> dict[str, Any]:
    return {"id": uid, "is_bot": False, "first_name": "Tester", "language_code": "ru"}


_update_ids = itertools.count(1)


def raw_message(uid: int, **content: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "message_id": next(_update_ids),
        "date": 1700000000,
        "chat": {"id": uid, "type": "private", "first_name": "Tester"},
        "from": _user(uid),
        **content,
    }
    text = content.get("text")
    if isinstance(text, str) and text.startswith("/"):
        msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {"update_id": next(_update_ids), "message": msg}


def raw_text(uid: int, text: str) -> dict[str, Any]:
    return raw_message(uid, text=text)


def raw_voice(uid: int) -> dict[str, Any]:
    voice = {"file_id": "v", "file_unique_id": "vu", "duration": 1, "mime_type": "audio/ogg"}
    return raw_message(uid, voice=voice)


def raw_callback(uid: int, data: str) -> dict[str, Any]:
    card = raw_message(uid, photo=_CARD_PHOTO)["message"]
    card["from"] = {"id": BOT_ID, "is_bot": True, "first_name": "Bot"}
    return {
        "update_id": next(_update_ids),
        "callback_query": {
            "id": str(next(_update_ids)),
            "from": _user(uid),
            "chat_instance": "ci",
            "data": data,
            "message": card,
        },
    }


class RecordingStorage(MemoryStorage):
    """
    MemoryStorage that logs every access, reads included.

    MemoryStorage is a defaultdict, so even ``get_state`` for an unseen key allocates a record; that is
    exactly what must not happen for an unauthorized update.
    """

    def __init__(self) -> None:
        super().__init__()
        self.accesses: list[tuple[str, StorageKey]] = []

    async def set_state(self, key: StorageKey, state: Any = None) -> None:
        self.accesses.append(("set_state", key))
        await super().set_state(key, state)

    async def get_state(self, key: StorageKey) -> Optional[str]:
        self.accesses.append(("get_state", key))
        return await super().get_state(key)

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        self.accesses.append(("set_data", key))
        await super().set_data(key, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        self.accesses.append(("get_data", key))
        return await super().get_data(key)


class Harness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, allowed: str, **env: str) -> None:
        # Paid providers configured on purpose: the gate must be the only thing stopping them.
        env = {
            "TEXT_PROVIDER": "openai",
            "IMAGE_PROVIDER": "openai",
            "STT_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-test-not-real",
            "ADMIN_USER_IDS": str(ADMIN),
            "ALLOWED_USER_IDS": allowed,
            **env,
        }
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        self._db_path = tmp_path / "bot.db"

        self.spies = SimpleNamespace(
            greeting=AsyncMock(return_value="Welcome back"),
            small_talk=AsyncMock(return_value="chat reply"),
            stt_main=AsyncMock(return_value="горы"),
            stt_profile=AsyncMock(return_value="Аня"),
            card=AsyncMock(
                return_value=GeneratedCard(
                    image_bytes=b"png",
                    texts=CardTexts(caption_html="<b>caption</b>", short_text=""),
                    image_prompt_en="final prompt",
                )
            ),
            text_only=AsyncMock(return_value=CardTexts(caption_html="<b>new caption</b>", short_text="")),
            image_only=AsyncMock(return_value=(b"png2", "new prompt")),
        )
        monkeypatch.setattr("handlers.main.generate_returning_start_greeting", self.spies.greeting)
        monkeypatch.setattr("handlers.main.generate_idle_small_talk", self.spies.small_talk)
        monkeypatch.setattr("handlers.main.transcribe_audio", self.spies.stt_main)
        monkeypatch.setattr("handlers.profile.transcribe_audio", self.spies.stt_profile)
        monkeypatch.setattr("handlers.main.run_card_generation", self.spies.card)
        monkeypatch.setattr("handlers.main.run_text_only", self.spies.text_only)
        monkeypatch.setattr("handlers.main.run_image_only", self.spies.image_only)

        # Backstop: any provider that slips past the spies still has to go through aiohttp.
        self.outbound: list[str] = []

        async def _blocked(session: Any, method: str, url: Any, **kwargs: Any) -> Any:
            self.outbound.append(f"{method} {url}")
            raise aiohttp.ClientError("network blocked in tests")

        monkeypatch.setattr(aiohttp.ClientSession, "_request", _blocked)

        self.session = FakeSession()
        self.bot = Bot(f"{BOT_ID}:TEST", session=self.session)
        # Same construction as bot.main(), including middleware order.
        self.dp = bot_module.build_dispatcher(get_settings().allowed_user_ids())
        # The FSM middleware reads ``self.storage`` on every update, so swapping it in observes the
        # production wiring without changing it.
        self.fsm_storage = RecordingStorage()
        self.dp.fsm.storage = self.fsm_storage

    # --- driving updates -------------------------------------------------

    async def feed(self, raw: dict[str, Any]) -> None:
        await self.dp.feed_raw_update(self.bot, raw)

    async def text(self, uid: int, text: str) -> None:
        await self.feed(raw_text(uid, text))

    async def voice(self, uid: int) -> None:
        await self.feed(raw_voice(uid))

    async def press(self, uid: int, data: str) -> None:
        await self.feed(raw_callback(uid, data))

    def update(self, raw: dict[str, Any]) -> Update:
        return Update.model_validate(raw, context={"bot": self.bot})

    # --- state -----------------------------------------------------------

    def ctx(self, uid: int) -> FSMContext:
        key = StorageKey(bot_id=BOT_ID, chat_id=uid, user_id=uid)
        return FSMContext(storage=self.dp.fsm.storage, key=key)

    async def seed_fsm(self, uid: int, state: Optional[State], **data: Any) -> None:
        ctx = self.ctx(uid)
        await ctx.set_state(state)
        await ctx.set_data(data)

    async def fsm(self, uid: int) -> tuple[Optional[str], dict[str, Any]]:
        ctx = self.ctx(uid)
        return await ctx.get_state(), await ctx.get_data()

    def assert_no_fsm_allocation(self) -> None:
        """No FSM storage call at all, hence no record: call before any ``fsm()``/``seed_fsm()`` helper."""
        assert self.fsm_storage.accesses == []
        assert len(self.fsm_storage.storage) == 0

    def seed_card(self, uid: int, original: Optional[bytes] = None) -> None:
        get_storage().save_last_card(
            uid,
            LastCardContext(
                occasion="occasion_loved",
                image_description="mountains",
                holiday="birthday",
                image_style="style_realistic",
                text_style="text_warm",
                lang="ru",
                image_prompt_en="mountains at dawn",
                photo_file_id="card-photo",
                caption_html="<b>old caption</b>",
                short_text="Old phrase" if original else "",
            ),
            original=original,
        )

    def seed_profile(self, uid: int, name: str = "Аня") -> None:
        get_storage().update_profile_preference(uid, display_name=name)

    def db(self) -> dict[str, list[tuple[Any, ...]]]:
        with closing(sqlite3.connect(self._db_path)) as conn:
            return {tbl: conn.execute(f"SELECT * FROM {tbl} ORDER BY 1, 2").fetchall() for tbl in _TABLES}

    # --- observations ----------------------------------------------------

    def sent_texts(self) -> list[str]:
        return [c.text for c in self.session.calls if type(c).__name__ == "SendMessage"]

    def paid_calls(self) -> list[str]:
        spy_calls = [name for name, spy in vars(self.spies).items() if spy.called]
        return spy_calls + self.outbound + [n for n in self.session.names() if n == "GetFile"]


@pytest.fixture
def make_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def factory(allowed: str = str(AUTH), **env: str) -> Harness:
        return Harness(monkeypatch, tmp_path, allowed=allowed, **env)

    yield factory

    # The production routers are module-level singletons and aiogram lets a router join only one
    # Dispatcher, so detach them to give the next test its own Dispatcher.
    for router in (admin_router, profile_router, main_router):
        router._parent_router = None


@pytest.fixture
def h(make_harness) -> Harness:
    return make_harness()


def assert_denied_message(h: Harness, lang: str = "ru") -> None:
    assert h.session.names() == ["SendMessage"]
    assert h.sent_texts() == [t("access_denied", lang)]


def assert_denied_callback(h: Harness, lang: str = "ru") -> None:
    assert h.session.names() == ["AnswerCallbackQuery"]
    assert h.session.calls[0].text == t("access_denied", lang)


# =========================================================================
# Authorized users keep the existing workflows
# =========================================================================


async def test_authorized_start_new_user_gets_onboarding(h: Harness) -> None:
    await h.text(AUTH, "/start")

    state, _ = await h.fsm(AUTH)
    assert state == ProfileStates.onboarding_name.state
    assert h.sent_texts()
    assert t("access_denied", "ru") not in h.sent_texts()
    assert h.paid_calls() == []


async def test_authorized_returning_start_reaches_llm_greeting(h: Harness) -> None:
    h.seed_profile(AUTH)

    await h.text(AUTH, "/start")

    h.spies.greeting.assert_awaited_once()
    assert "Welcome back" in h.sent_texts()


async def test_authorized_idle_chat_reaches_llm_small_talk(h: Harness) -> None:
    h.seed_profile(AUTH)

    await h.text(AUTH, "давай поболтаем")

    h.spies.small_talk.assert_awaited_once()
    assert "chat reply" in h.sent_texts()


async def test_authorized_voice_reaches_stt(h: Harness) -> None:
    await h.seed_fsm(AUTH, CardStates.image_description, lang="ru", image_idea_mode="custom")

    await h.voice(AUTH)

    h.spies.stt_main.assert_awaited_once()
    assert "GetFile" in h.session.names()


async def test_authorized_wizard_generates_a_card(h: Harness) -> None:
    await h.seed_fsm(
        AUTH,
        CardStates.signature_toggle,
        lang="ru",
        occasion="occasion_loved",
        image_description="mountains",
        holiday="birthday",
        image_style="style_realistic",
        text_style="text_warm",
    )

    await h.press(AUTH, WIZARD_SIGNATURE_NO)

    h.spies.card.assert_awaited_once()
    assert "SendPhoto" in h.session.names()
    assert get_storage().get_daily_count(AUTH) == 1
    assert get_storage().get_last_card(AUTH) is not None


async def test_authorized_regen_text_reaches_provider(h: Harness) -> None:
    h.seed_card(AUTH)

    await h.press(AUTH, "regen_text")

    h.spies.text_only.assert_awaited_once()
    assert get_storage().get_daily_count(AUTH) == 1


async def test_authorized_regen_image_reaches_provider(h: Harness) -> None:
    h.seed_card(AUTH)

    await h.press(AUTH, "regen_image")

    h.spies.image_only.assert_awaited_once()
    assert get_storage().get_daily_count(AUTH) == 1


async def test_authorized_regen_card_lang_reaches_provider(h: Harness) -> None:
    h.seed_card(AUTH)

    await h.press(AUTH, "regen_card_lang")

    h.spies.text_only.assert_awaited_once()


async def test_authorized_new_caption_redraws_the_phrase_on_the_stored_original(h: Harness) -> None:
    original = _png_bytes()
    h.seed_card(AUTH, original=original)
    h.spies.text_only.return_value = CardTexts(caption_html="<b>fresh</b>", short_text="Fresh phrase")

    await h.press(AUTH, "regen_text")

    h.spies.text_only.assert_awaited_once()
    h.spies.image_only.assert_not_called()  # the image is reused, not generated again
    photos = [c for c in h.session.calls if type(c).__name__ == "SendPhoto"]
    assert len(photos) == 1
    sent = photos[0].photo.data
    assert sent != original and Image.open(io.BytesIO(sent)).size == (256, 256)
    ctx, stored_original = get_storage().get_last_card_with_original(AUTH)
    assert stored_original == original  # the clean original is never replaced by the rendered card
    assert (ctx.short_text, ctx.caption_html) == ("Fresh phrase", "<b>fresh</b>")  # type: ignore[union-attr]


UNAUTHORIZED_REGEN_PRESS = pytest.mark.parametrize(
    ("uid", "data"),
    [(u, d) for u in (STRANGER, ADMIN) for d in ("regen_repeat", "regen_text", "regen_image", "regen_card_lang")],
)


@UNAUTHORIZED_REGEN_PRESS
async def test_unauthorized_regeneration_never_renders_or_touches_the_stored_original(
    h: Harness, monkeypatch: pytest.MonkeyPatch, uid: int, data: str
) -> None:
    render = AsyncMock(return_value=(b"never", True))
    monkeypatch.setattr("handlers.main.render_card_image", render)
    h.seed_card(uid, original=_png_bytes())
    before = h.db()

    await h.press(uid, data)

    render.assert_not_called()
    assert h.paid_calls() == []
    assert h.db() == before  # context and original image rows are byte-identical
    assert "SendPhoto" not in h.session.names()
    assert_denied_callback(h)


async def test_allowlisted_admin_keeps_admin_commands(make_harness) -> None:
    h = make_harness(allowed=f"{AUTH},{ADMIN}")

    await h.text(ADMIN, "/stats")

    assert any(text.startswith("Admin stats") for text in h.sent_texts())


# =========================================================================
# Unauthorized users: no replies beyond the notice, no cost, no data
# =========================================================================

# A stranger, and an admin who is not on the allowlist (admin status grants nothing here).
UNAUTHORIZED = pytest.mark.parametrize("uid", [STRANGER, ADMIN], ids=["stranger", "admin-not-allowlisted"])


@UNAUTHORIZED
async def test_unauthorized_start_does_not_call_llm_or_touch_data(h: Harness, uid: int) -> None:
    h.seed_profile(uid)  # even a known profile (returning-user LLM greeting path) must not be reached
    before = h.db()

    await h.text(uid, "/start")

    h.spies.greeting.assert_not_called()
    h.spies.small_talk.assert_not_called()
    assert h.paid_calls() == []
    assert h.db() == before
    assert await h.fsm(uid) == (None, {})
    assert_denied_message(h)


@UNAUTHORIZED
async def test_unauthorized_new_user_start_creates_nothing(h: Harness, uid: int) -> None:
    before = h.db()

    await h.text(uid, "/start")

    assert h.db() == before
    assert get_storage().get_user_lang(uid) is None
    assert get_storage().user_needs_profile_onboarding(uid)
    assert await h.fsm(uid) == (None, {})
    assert_denied_message(h)


@UNAUTHORIZED
async def test_unauthorized_voice_does_not_call_stt(h: Harness, uid: int) -> None:
    # STT is configured and the wizard is waiting for a custom image idea: the handler would transcribe.
    await h.seed_fsm(uid, CardStates.image_description, lang="ru", image_idea_mode="custom")
    before = h.db()

    await h.voice(uid)

    h.spies.stt_main.assert_not_called()
    h.spies.stt_profile.assert_not_called()
    assert "GetFile" not in h.session.names()
    assert h.paid_calls() == []
    assert h.db() == before
    assert_denied_message(h)


@UNAUTHORIZED
async def test_unauthorized_voice_in_onboarding_does_not_call_stt(h: Harness, uid: int) -> None:
    await h.seed_fsm(uid, ProfileStates.confirming_name, lang="ru")

    await h.voice(uid)

    h.spies.stt_profile.assert_not_called()
    h.spies.stt_main.assert_not_called()
    assert_denied_message(h)


@UNAUTHORIZED
async def test_unauthorized_idle_chat_does_not_call_small_talk(h: Harness, uid: int) -> None:
    h.seed_profile(uid)

    await h.text(uid, "давай поболтаем")

    h.spies.small_talk.assert_not_called()
    assert h.paid_calls() == []
    assert_denied_message(h)


_ALL_STATES = [None, *CardStates.__all_states__, *ProfileStates.__all_states__]


@UNAUTHORIZED
@pytest.mark.parametrize("state", _ALL_STATES, ids=lambda s: s.state if s else "idle")
async def test_unauthorized_text_in_any_wizard_state_is_inert(h: Harness, uid: int, state: Optional[State]) -> None:
    seeded = {
        "lang": "ru",
        "occasion": "occasion_loved",
        "image_description": "mountains",
        "holiday": "birthday",
        "image_style": "style_realistic",
        "text_style": "text_warm",
        "image_idea_mode": "custom",
    }
    await h.seed_fsm(uid, state, **seeded)
    before_db = h.db()
    before_fsm = await h.fsm(uid)

    await h.text(uid, "Anna")

    assert h.paid_calls() == []
    assert h.db() == before_db
    assert await h.fsm(uid) == before_fsm
    assert_denied_message(h)


@UNAUTHORIZED
async def test_unauthorized_signature_answer_cannot_start_generation(h: Harness, uid: int) -> None:
    await h.seed_fsm(
        uid,
        CardStates.sender_signature,
        lang="ru",
        occasion="occasion_loved",
        image_description="mountains",
        holiday="birthday",
    )
    before = h.db()

    await h.text(uid, "С любовью, Аня")

    h.spies.card.assert_not_called()
    assert h.paid_calls() == []
    assert h.db() == before
    assert (await h.fsm(uid))[0] == CardStates.sender_signature.state


@UNAUTHORIZED
async def test_unauthorized_signature_button_cannot_start_generation(h: Harness, uid: int) -> None:
    await h.seed_fsm(
        uid,
        CardStates.signature_toggle,
        lang="ru",
        occasion="occasion_loved",
        image_description="mountains",
        holiday="birthday",
        image_style="style_realistic",
        text_style="text_warm",
    )
    before = h.db()

    await h.press(uid, WIZARD_SIGNATURE_NO)

    h.spies.card.assert_not_called()
    assert h.paid_calls() == []
    assert h.db() == before
    assert (await h.fsm(uid))[0] == CardStates.signature_toggle.state
    assert_denied_callback(h)


@UNAUTHORIZED
@pytest.mark.parametrize("data", ["regen_repeat", "regen_text", "regen_image", "regen_card_lang"])
async def test_unauthorized_regeneration_callbacks_cannot_reach_providers(h: Harness, uid: int, data: str) -> None:
    h.seed_card(uid)
    before = h.db()

    await h.press(uid, data)

    h.spies.text_only.assert_not_called()
    h.spies.image_only.assert_not_called()
    assert h.paid_calls() == []
    assert h.db() == before
    assert get_storage().get_daily_count(uid) == 0
    assert_denied_callback(h)  # acknowledged, and no photo/message was sent


@UNAUTHORIZED
@pytest.mark.parametrize(
    "data",
    [
        "action_create_card",
        "action_help",
        "lang_ru",
        "lang_en",
        "occasion_loved",
        "style_realistic",
        "text_warm",
        "profile:main",
        "profile:dev_reset",
        "profile:set:lang:en",
        "change_lang",
        "no-such-button",
    ],
)
async def test_unauthorized_callbacks_are_always_acknowledged_and_inert(h: Harness, uid: int, data: str) -> None:
    before = h.db()

    await h.press(uid, data)

    assert h.paid_calls() == []
    assert h.db() == before
    assert_denied_callback(h)


@UNAUTHORIZED
@pytest.mark.parametrize(
    "command",
    [
        "/help",
        "/lang",
        "/cancel",
        "/stats",
        "/smalltalk_on",
        "/smalltalk_off",
        "/maintenance Back soon",
        "/dev_reset_me",
        "/no_such_command",
    ],
)
async def test_unauthorized_commands_including_admin_ones_are_denied(h: Harness, uid: int, command: str) -> None:
    h.seed_profile(uid)
    await h.seed_fsm(uid, CardStates.holiday, lang="ru")
    before_db = h.db()
    before_fsm = await h.fsm(uid)

    await h.text(uid, command)

    assert h.db() == before_db  # no kv flip, no profile reset, no maintenance banner
    assert await h.fsm(uid) == before_fsm  # /cancel and friends did not clear the wizard
    assert h.paid_calls() == []
    assert_denied_message(h)


async def test_unauthorized_admin_cannot_change_bot_settings(h: Harness) -> None:
    for command in ("/smalltalk_off", "/maintenance Back soon"):
        await h.text(ADMIN, command)

    storage = get_storage()
    assert storage.is_small_talk_enabled()
    assert storage.get_maintenance_message() == ""


async def test_unconfigured_allowlist_denies_everyone_including_admin(make_harness) -> None:
    h = make_harness(allowed="")

    for uid in (AUTH, STRANGER, ADMIN):
        await h.text(uid, "/start")

    assert h.paid_calls() == []
    assert h.sent_texts() == [t("access_denied", "ru")] * 3


async def test_malformed_allowlist_denies_everyone(make_harness) -> None:
    h = make_harness(allowed=f"{AUTH},not-a-number")

    await h.text(AUTH, "/start")
    await h.press(AUTH, "regen_text")

    assert h.paid_calls() == []
    assert h.session.names() == ["SendMessage", "AnswerCallbackQuery"]


@pytest.mark.parametrize("kind", ["edited_message", "channel_post", "inline_query"])
async def test_other_update_kinds_are_dropped_silently(h: Harness, kind: str) -> None:
    base = raw_text(STRANGER, "hi")["message"]
    payloads: dict[str, dict[str, Any]] = {
        "edited_message": base,
        # no sender at all: the user cannot be determined, so the update is dropped
        "channel_post": {k: v for k, v in base.items() if k != "from"} | {"chat": {"id": -100, "type": "channel", "title": "c"}},
        "inline_query": {"id": "1", "from": _user(STRANGER), "query": "q", "offset": ""},
    }
    before = h.db()

    await h.feed({"update_id": next(_update_ids), kind: payloads[kind]})

    assert h.session.calls == []
    assert h.paid_calls() == []
    assert h.db() == before
    h.assert_no_fsm_allocation()


# =========================================================================
# Access runs before FSM: a rejected update never allocates state
# =========================================================================


def test_production_dispatcher_runs_access_before_fsm(h: Harness) -> None:
    # Structural pin of build_dispatcher(): aiogram appends user outer middlewares *after* the FSM
    # middleware it registers itself, so order is only right if the FSM middleware is registered last.
    assert [type(m) for m in h.dp.update.outer_middleware] == [
        ErrorsMiddleware,
        UserContextMiddleware,
        AccessMiddleware,
        FSMContextMiddleware,
    ]
    assert [type(m) for m in h.dp.update.middleware] == [MaintenanceMiddleware]


_UNAUTHORIZED_UPDATES = {
    "start": lambda uid: raw_text(uid, "/start"),
    "text": lambda uid: raw_text(uid, "Anna"),
    "voice": raw_voice,
    "callback-wizard": lambda uid: raw_callback(uid, WIZARD_SIGNATURE_NO),
    "callback-regen": lambda uid: raw_callback(uid, "regen_text"),
    "admin-command": lambda uid: raw_text(uid, "/stats"),
}


@UNAUTHORIZED
@pytest.mark.parametrize("kind", list(_UNAUTHORIZED_UPDATES))
async def test_unauthorized_update_is_rejected_before_fsm_allocation(h: Harness, uid: int, kind: str) -> None:
    h.seed_profile(uid)
    h.seed_card(uid)
    before = h.db()

    await h.feed(_UNAUTHORIZED_UPDATES[kind](uid))

    h.assert_no_fsm_allocation()
    assert h.paid_calls() == []
    assert h.db() == before
    if kind.startswith("callback"):
        assert_denied_callback(h)  # still acknowledged, toast carries the notice
    else:
        assert_denied_message(h)


@UNAUTHORIZED
async def test_unauthorized_update_leaves_existing_fsm_records_untouched(h: Harness, uid: int) -> None:
    await h.seed_fsm(uid, CardStates.sender_signature, lang="ru", occasion="occasion_loved")
    seeded = {key: (rec.state, dict(rec.data)) for key, rec in h.fsm_storage.storage.items()}
    h.fsm_storage.accesses.clear()

    await h.text(uid, "С любовью, Аня")
    await h.press(uid, WIZARD_SIGNATURE_NO)

    assert h.fsm_storage.accesses == []
    assert {key: (rec.state, dict(rec.data)) for key, rec in h.fsm_storage.storage.items()} == seeded


async def test_only_authorized_users_get_fsm_records(h: Harness) -> None:
    for uid in (STRANGER, ADMIN, AUTH):
        await h.text(uid, "/start")

    # Positive control: FSM is not disabled, it just comes after the gate.
    assert set(h.fsm_storage.storage) == {StorageKey(bot_id=BOT_ID, chat_id=AUTH, user_id=AUTH)}
    assert {key.user_id for _, key in h.fsm_storage.accesses} == {AUTH}
    assert (await h.fsm(AUTH))[0] == ProfileStates.onboarding_name.state


# =========================================================================
# Notice language, noise, ordering
# =========================================================================


async def test_notice_is_english_for_a_stored_english_user(h: Harness) -> None:
    get_storage().set_user_lang(STRANGER, "en")
    before = h.db()

    await h.text(STRANGER, "hello")

    assert_denied_message(h, "en")
    assert h.db() == before  # reading the stored language writes nothing


async def test_notice_defaults_to_russian_for_unknown_user(h: Harness) -> None:
    await h.text(STRANGER, "hello there")
    assert_denied_message(h, "ru")


def test_callback_toast_fits_telegram_limit() -> None:
    for lang in ("ru", "en"):
        assert len(t("access_denied", lang)) <= 200


async def test_denial_does_not_use_any_llm(h: Harness) -> None:
    await h.text(STRANGER, "/start")
    await h.text(STRANGER, "hi")
    await h.press(STRANGER, "regen_text")
    assert h.paid_calls() == []


async def test_maintenance_banner_does_not_replace_access_denial(h: Harness) -> None:
    get_storage().set_maintenance_message("Back soon")

    await h.text(STRANGER, "hi")
    assert h.sent_texts() == [t("access_denied", "ru")]


async def test_maintenance_still_applies_to_authorized_non_admins(h: Harness) -> None:
    get_storage().set_maintenance_message("Back soon")

    await h.text(AUTH, "hi")

    assert h.sent_texts() == ["Back soon"]


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_repeated_denials_send_one_notice_per_window(h: Harness) -> None:
    clock = _Clock()
    mw = AccessMiddleware(frozenset(), clock=clock)
    inner = AsyncMock()

    for _ in range(3):
        await mw(inner, h.update(raw_text(STRANGER, "hi")), {})
    assert h.session.names() == ["SendMessage"]

    clock.now += ACCESS_NOTICE_INTERVAL_SECONDS + 1
    await mw(inner, h.update(raw_text(STRANGER, "hi again")), {})
    assert h.session.names() == ["SendMessage", "SendMessage"]
    inner.assert_not_called()


async def test_throttle_is_per_user(h: Harness) -> None:
    mw = AccessMiddleware(frozenset(), clock=_Clock())
    inner = AsyncMock()

    await mw(inner, h.update(raw_text(STRANGER, "hi")), {})
    await mw(inner, h.update(raw_text(ADMIN, "hi")), {})

    assert h.session.names() == ["SendMessage", "SendMessage"]


async def test_throttled_user_callbacks_are_still_acknowledged(h: Harness) -> None:
    mw = AccessMiddleware(frozenset(), clock=_Clock())
    inner = AsyncMock()

    await mw(inner, h.update(raw_text(STRANGER, "hi")), {})
    for _ in range(3):
        await mw(inner, h.update(raw_callback(STRANGER, "regen_text")), {})

    assert h.session.names() == ["SendMessage"] + ["AnswerCallbackQuery"] * 3
    inner.assert_not_called()


async def test_notice_cache_is_bounded(h: Harness) -> None:
    mw = AccessMiddleware(frozenset(), clock=_Clock())
    inner = AsyncMock()

    for uid in range(1, 2200):
        await mw(inner, h.update(raw_text(uid, "hi")), {})

    assert len(mw._last_notice) <= 1024


async def test_failed_denial_reply_does_not_raise(h: Harness) -> None:
    h.session.fail_answer_callback = True
    mw = AccessMiddleware(frozenset(), clock=_Clock())
    inner = AsyncMock()

    await mw(inner, h.update(raw_callback(STRANGER, "regen_text")), {})

    assert any(isinstance(c, AnswerCallbackQuery) for c in h.session.calls)
    inner.assert_not_called()


async def test_allowed_user_passes_through_to_handler(h: Harness) -> None:
    mw = AccessMiddleware(frozenset({AUTH}))
    inner = AsyncMock(return_value="handled")
    update = h.update(raw_text(AUTH, "hi"))

    assert await mw(inner, update, {"k": 1}) == "handled"
    inner.assert_awaited_once_with(update, {"k": 1})
    assert h.session.calls == []


# =========================================================================
# Daily limits are unchanged and independent of the allowlist
# =========================================================================


async def test_allowlisted_user_at_daily_cap_is_still_rate_limited(make_harness) -> None:
    h = make_harness(DAILY_GENERATION_LIMIT="2")
    h.seed_card(AUTH)
    for _ in range(2):
        get_storage().increment_generation(AUTH)

    await h.press(AUTH, "regen_text")

    h.spies.text_only.assert_not_called()
    assert h.session.names() == ["AnswerCallbackQuery"]
    assert h.session.calls[0].text == t("rate_limited", "ru")
    assert h.session.calls[0].show_alert is True
    assert get_storage().get_daily_count(AUTH) == 2


async def test_allowlisted_user_under_cap_counts_one_per_generation(make_harness) -> None:
    h = make_harness(DAILY_GENERATION_LIMIT="2")
    h.seed_card(AUTH)

    await h.press(AUTH, "regen_text")
    await h.press(AUTH, "regen_image")
    await h.press(AUTH, "regen_text")  # third attempt: over the cap

    assert h.spies.text_only.await_count == 1
    assert h.spies.image_only.await_count == 1
    assert get_storage().get_daily_count(AUTH) == 2


async def test_allowlisted_admin_remains_exempt_from_daily_cap(make_harness) -> None:
    h = make_harness(allowed=f"{AUTH},{ADMIN}", DAILY_GENERATION_LIMIT="1")
    h.seed_card(ADMIN)
    get_storage().increment_generation(ADMIN)

    await h.press(ADMIN, "regen_text")

    h.spies.text_only.assert_awaited_once()
    assert get_storage().get_daily_count(ADMIN) == 1  # admins are not counted


async def test_denied_attempts_never_consume_the_daily_cap(make_harness) -> None:
    h = make_harness(DAILY_GENERATION_LIMIT="1")
    h.seed_card(STRANGER)

    for _ in range(5):
        await h.press(STRANGER, "regen_text")

    assert get_storage().get_daily_count(STRANGER) == 0
    assert h.db()["generation_log"] == []
