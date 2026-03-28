"""
Maintenance mode: block non-admins while admin message is set.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from config import get_settings
from services.storage import get_storage

logger = logging.getLogger(__name__)


def _user_id_from_update(update: Update) -> Optional[int]:
    if update.message and update.message.from_user:
        return update.message.from_user.id
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user.id
    if update.edited_message and update.edited_message.from_user:
        return update.edited_message.from_user.id
    return None


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
