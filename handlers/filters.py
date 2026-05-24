"""Aiogram filters."""
from aiogram.filters import Filter
from aiogram.types import Message

from config import get_settings


def is_admin_user_id(user_id: int) -> bool:
    return user_id in get_settings().admin_ids()


class AdminFilter(Filter):
    """True if message author is in ADMIN_USER_IDS."""

    async def __call__(self, message: Message) -> bool:
        u = message.from_user
        if not u:
            return False
        return is_admin_user_id(u.id)
