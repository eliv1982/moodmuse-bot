"""
Shared pytest fixtures.

The suite must not depend on a developer's ``.env`` or ambient credentials. ``config.py`` loads
``.env`` into ``os.environ`` at import time and ``Settings`` also reads ``env_file=".env"``, so
every test starts from a scrubbed environment that holds only a fake ``BOT_TOKEN``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

from config import Settings
from services.storage import init_storage, reset_storage_for_tests

# Everything Settings (or flow logging) reads from the environment.
_CONFIG_ENV_NAMES = frozenset(name.upper() for name in Settings.model_fields) | {"DEBUG_FLOW_LOGS"}


@pytest.fixture(autouse=True)
def _hermetic_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.upper() in _CONFIG_ENV_NAMES:
            monkeypatch.delenv(key)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("BOT_TOKEN", "test-token")


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path) -> Iterator[None]:
    # get_storage() falls back to data/bot.db (the runtime database) when not initialised.
    reset_storage_for_tests()
    init_storage(tmp_path / "bot.db")
    yield
    reset_storage_for_tests()
