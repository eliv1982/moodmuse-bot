"""
Update-level gates: private access (allowlist) and maintenance mode.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import TelegramObject, Update

from config import get_settings
from services.storage import get_storage
from utils.i18n import Lang, t

logger = logging.getLogger(__name__)

# One denial reply per user per window; callback queries are always acknowledged regardless.
ACCESS_NOTICE_INTERVAL_SECONDS = 600.0
_ACCESS_NOTICE_CACHE_SIZE = 1024


def _user_id_from_update(update: Update) -> Optional[int]:
    if update.message and update.message.from_user:
        return update.message.from_user.id
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user.id
    if update.edited_message and update.edited_message.from_user:
        return update.edited_message.from_user.id
    return None


def _stored_lang(user_id: Optional[int]) -> Lang:
    """Language already saved for this user (read-only); Russian when unknown or unreadable."""
    if user_id is None:
        return "ru"
    try:
        return "en" if get_storage().get_user_lang(user_id) == "en" else "ru"
    except Exception:
        return "ru"


class AccessMiddleware(BaseMiddleware):
    """
    Private-bot gate: only allowlisted users reach any handler.

    Registered as an outer middleware on ``dp.update``, ahead of the FSM middleware (see ``build_dispatcher``),
    so commands, onboarding and wizard steps, text, voice, callbacks, regeneration and admin commands are all
    covered in one place, and nothing behind it (FSM state, LLM/STT/image providers, storage writes) runs
    for anyone else. Admin status does not bypass it. An update whose
    user cannot be determined is dropped.
    """

    def __init__(
        self,
        allowed_user_ids: Iterable[int],
        *,
        notice_interval: float = ACCESS_NOTICE_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._allowed = frozenset(allowed_user_ids)
        self._notice_interval = notice_interval
        self._clock = clock
        self._last_notice: OrderedDict[int, float] = OrderedDict()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return None
        uid = _user_id_from_update(event)
        if uid is not None and uid in self._allowed:
            return await handler(event, data)
        await self._deny(event, uid)
        return None

    def _should_notify(self, user_id: int) -> bool:
        now = self._clock()
        last = self._last_notice.get(user_id)
        if last is not None and now - last < self._notice_interval:
            return False
        self._last_notice[user_id] = now
        self._last_notice.move_to_end(user_id)
        while len(self._last_notice) > _ACCESS_NOTICE_CACHE_SIZE:
            self._last_notice.popitem(last=False)
        return True

    async def _deny(self, update: Update, uid: Optional[int]) -> None:
        # Without a known user there is nobody to notify (and nothing to throttle on).
        notify = uid is not None and self._should_notify(uid)
        if notify:
            logger.info(
                "access_denied user_id=%s",
                uid,
                extra={"user_id": uid, "event": "access_denied"},
            )
        text = t("access_denied", _stored_lang(uid))
        try:
            if update.callback_query:
                # Always acknowledge, otherwise the button spinner hangs; the toast carries the notice.
                await update.callback_query.answer(text)
            elif update.message and notify:
                await update.message.answer(text)
        except TelegramAPIError:
            logger.debug("access_denied_reply_failed", extra={"user_id": uid, "event": "access_denied"})


class MaintenanceMiddleware(BaseMiddleware):
    """If maintenance_message is set, non-admins get that text and the update is not processed further."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        settings = get_settings()
        storage = get_storage()
        note = storage.get_maintenance_message().strip()
        if not note:
            return await handler(event, data)

        uid = _user_id_from_update(event)
        if uid is not None and uid in settings.admin_ids():
            return await handler(event, data)

        if event.message:
            await event.message.answer(note)
        elif event.edited_message:
            await event.edited_message.answer(note)
        elif event.callback_query:
            await event.callback_query.answer()
            if event.callback_query.message:
                await event.callback_query.message.answer(note)
        logger.info(
            "maintenance_block",
            extra={"user_id": uid, "event": "maintenance_block"},
        )
        return None
