"""
One-at-a-time guard per user for everything that replaces the user's single stored card.

A wizard run, "new caption", "new image" and the language switch each read the stored card, wait tens of
seconds on providers, then write the card back. If two of them overlapped, a late writer could pair its
text with another run's image. So a second one is refused with a "still preparing" notice instead of being
queued behind a paid call, and the card is always read after the lock is taken.

Usage: check ``card_lock(uid).locked()`` first (no ``await`` in between), then ``async with`` it.
"""
from __future__ import annotations

import asyncio

_locks: dict[int, asyncio.Lock] = {}


def card_lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = _locks[user_id] = asyncio.Lock()
    return lock
