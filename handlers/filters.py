"""Aiogram filters."""
from aiogram.filters import Filter
from aiogram.types import Message

from config import get_settings


class AdminFilter(Filter):
    """True if message author is in ADMIN_USER_IDS."""

    async def __call__(self, message: Message) -> bool:
        u = message.from_user
        if not u:
            return False
        return u.id in get_settings().admin_ids()
