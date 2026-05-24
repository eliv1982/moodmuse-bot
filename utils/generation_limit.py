"""
Daily card generation limit checks (SQLite daily_counts + settings).
"""
from __future__ import annotations

from config import Settings
from services.storage import get_storage


def effective_daily_limit(settings: Settings) -> int | None:
    """Max generations per user per UTC day, or None when unlimited (limit <= 0)."""
    limit = settings.DAILY_GENERATION_LIMIT
    if limit <= 0:
        return None
    return limit


def can_consume_generation(user_id: int, settings: Settings) -> bool:
    """True if the user may start another paid generation today."""
    if user_id in settings.admin_ids():
        return True
    limit = effective_daily_limit(settings)
    if limit is None:
        return True
    return get_storage().get_daily_count(user_id) < limit


def should_increment_daily_count(user_id: int, settings: Settings) -> bool:
    """Admins bypass counting; regular users increment only after successful generation."""
    return user_id not in settings.admin_ids()
