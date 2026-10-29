"""
Shared driver for the creation-flow tests: the production dispatcher (access gate, FSM, routers), a fake
Telegram session, and mocks for every paid call (text model, image model, speech recognition).

The access-control harness is reused as-is; this module only adds creation-specific spies and helpers to
read what the bot showed and press its buttons.
"""
from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardMarkup
from PIL import Image

from services.brief_ai import Extraction, heuristic_extraction
from services.card_generation import CardTexts, GeneratedCard
from services.storage import get_storage
from tests.test_access_control import AUTH, Harness
from utils import creation_ui as ui
from utils.creative_brief import (
    CAPTION_AI,
    CAPTION_USER,
    CreativeBrief,
    inscription_to_draw,
    resolve_caption_mode,
)
from utils.i18n import t

__all__ = ["AUTH", "CreationDriver", "Extraction", "png_bytes", "make_driver"]


def png_bytes(size: int = 256) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (40, 60, 90)).save(buf, format="PNG")
    return buf.getvalue()


CLEAN_IMAGE = png_bytes()


def fake_generation(settings: Any, brief: CreativeBrief, *, profile_prefs: Any = None) -> GeneratedCard:
    """What run_brief_generation hands back, without any provider: the brief's own inscription, unchanged."""
    caption = "<b>AI message</b>" if resolve_caption_mode(brief) == CAPTION_AI else ""
    if resolve_caption_mode(brief) == CAPTION_USER:
        caption = brief.caption_text
    return GeneratedCard(
        image_bytes=CLEAN_IMAGE,
        texts=CardTexts(caption_html=caption, short_text=inscription_to_draw(brief)),
        image_prompt_en="final prompt",
    )


async def fake_render(original: bytes, short_text: str, *, exact: bool = False) -> tuple[bytes, bool]:
    if not (short_text or "").strip():
        return original, False
    return b"RENDERED[" + short_text.encode() + b"]", True


class CreationDriver:
    """Drives one authorised user through the creation flow and reports what the bot showed."""

    def __init__(self, h: Harness, spies: SimpleNamespace) -> None:
        self.h = h
        self.spies = spies

    # ---- input -------------------------------------------------------

    async def start(self, uid: int = AUTH) -> None:
        await self.h.text(uid, t("btn_create_card", "ru"))

    async def say(self, text: str, uid: int = AUTH) -> None:
        await self.h.text(uid, text)

    async def tap(self, data: str, uid: int = AUTH) -> None:
        await self.h.press(uid, data)

    async def tap_label(self, label: str, uid: int = AUTH) -> None:
        for text, data in self.buttons():
            if label in text:
                await self.tap(data, uid)
                return
        raise AssertionError(f"no button containing {label!r} in {self.buttons()}")

    # ---- observation -------------------------------------------------

    def _screens(self) -> list[Any]:
        return [c for c in self.h.session.calls if type(c).__name__ in ("SendMessage", "EditMessageText")]

    def screen(self) -> str:
        """Text of the newest message the bot sent or edited."""
        return self._screens()[-1].text

    def markup(self) -> Optional[InlineKeyboardMarkup]:
        for call in reversed(self._screens()):
            markup = getattr(call, "reply_markup", None)
            if isinstance(markup, InlineKeyboardMarkup):
                return markup
        return None

    def buttons(self) -> list[tuple[str, str]]:
        markup = self.markup()
        if markup is None:
            return []
        return [(b.text, b.callback_data or "") for row in markup.inline_keyboard for b in row]

    def callbacks(self) -> list[str]:
        return [data for _, data in self.buttons()]

    def all_texts(self) -> list[str]:
        return [c.text for c in self._screens()]

    def photos(self) -> list[Any]:
        return [c for c in self.h.session.calls if type(c).__name__ == "SendPhoto"]

    def callback_answers(self) -> list[Any]:
        return [c for c in self.h.session.calls if type(c).__name__ == "AnswerCallbackQuery"]

    async def fsm(self, uid: int = AUTH) -> tuple[Optional[str], dict[str, Any]]:
        return await self.h.fsm(uid)

    async def state(self, uid: int = AUTH) -> Optional[str]:
        return (await self.fsm(uid))[0]

    async def brief(self, uid: int = AUTH) -> CreativeBrief:
        _, data = await self.fsm(uid)
        return CreativeBrief.from_dict(data.get("brief"))

    # ---- shortcuts through the steps --------------------------------------------------

    async def to_confirmation_guided(
        self,
        *,
        purpose: str = "birthday",
        mood: str = "warm",
        style: str = "style_watercolor",
        inscription: Optional[str] = "С днём рождения!",
    ) -> None:
        """Mode 1 from the menu button to the confirmation screen."""
        await self.start()
        await self.tap(ui.CB_MODE + ui.MODE_GUIDED)
        await self.tap(ui.CB_PURPOSE + purpose)
        await self.tap(ui.CB_MOOD + mood)
        await self.tap(ui.CB_STYLE + style)
        if inscription is None:
            await self.tap(ui.CB_INSCRIPTION + ui.INSC_NONE)
        else:
            await self.tap(ui.CB_INSCRIPTION + ui.INSC_TEXT)
            await self.say(inscription)
        await self.tap(ui.CB_NEXT)

    async def to_confirmation_free(self, description: str) -> None:
        await self.start()
        await self.tap(ui.CB_MODE + ui.MODE_FREE)
        await self.say(description)


@pytest.fixture
def make_driver(make_harness, monkeypatch: pytest.MonkeyPatch):
    """Factory for a driver around the production dispatcher with all paid calls mocked."""

    def factory(**env: str) -> CreationDriver:
        h = make_harness(**env)
        h.seed_profile(AUTH)
        spies = SimpleNamespace(
            extract=AsyncMock(side_effect=lambda text, settings: heuristic_extraction(text)),
            suggest=AsyncMock(return_value="С днём рождения!"),
            generate=AsyncMock(side_effect=fake_generation),
            render=AsyncMock(side_effect=fake_render),
            stt=AsyncMock(return_value="закат над морем"),
        )
        monkeypatch.setattr("handlers.creation.extract_brief_fields", spies.extract)
        monkeypatch.setattr("handlers.creation.suggest_inscription", spies.suggest)
        monkeypatch.setattr("handlers.creation.run_brief_generation", spies.generate)
        monkeypatch.setattr("handlers.main.render_card_image", spies.render)
        monkeypatch.setattr("handlers.main._transcribe_voice_message", spies.stt)
        return CreationDriver(h, spies)

    return factory


@pytest.fixture
def cr(make_driver) -> CreationDriver:
    return make_driver()


def stored_card() -> Any:
    ctx, original = get_storage().get_last_card_with_original(AUTH)
    return SimpleNamespace(ctx=ctx, original=original)
