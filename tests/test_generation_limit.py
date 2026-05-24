"""Daily generation limit and admin bypass."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import Settings
from handlers.filters import is_admin_user_id
from services.storage import get_storage, init_storage, reset_storage_for_tests
from utils.generation_limit import (
    can_consume_generation,
    effective_daily_limit,
    should_increment_daily_count,
)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "DAILY_GENERATION_LIMIT": 5,
        "ADMIN_USER_IDS": "",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_daily_generation_limit_defaults_to_five() -> None:
    s = _settings()
    assert s.DAILY_GENERATION_LIMIT == 5


def test_daily_generation_limit_invalid_env_defaults_to_five() -> None:
    s = _settings(DAILY_GENERATION_LIMIT="not-a-number")
    assert s.DAILY_GENERATION_LIMIT == 5
    s2 = _settings(DAILY_GENERATION_LIMIT=-3)
    assert s2.DAILY_GENERATION_LIMIT == 5


def test_daily_generation_limit_zero_is_unlimited() -> None:
    s = _settings(DAILY_GENERATION_LIMIT=0)
    assert effective_daily_limit(s) is None
    uid = 1
    for _ in range(20):
        assert can_consume_generation(uid, s) is True


def test_admin_ids_parsing_comma_separated() -> None:
    s = _settings(ADMIN_USER_IDS="123, 456 ,bad,789")
    assert s.admin_ids() == [123, 456, 789]


def test_admin_ids_invalid_values_do_not_crash() -> None:
    s = _settings(ADMIN_USER_IDS="abc,xyz")
    assert s.admin_ids() == []


def test_regular_user_under_limit_can_generate(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "limit.db")
    uid = 100
    settings = _settings(DAILY_GENERATION_LIMIT=5, ADMIN_USER_IDS="")
    for _ in range(4):
        get_storage().increment_generation(uid)
    assert can_consume_generation(uid, settings) is True
    reset_storage_for_tests()


def test_regular_user_at_limit_is_blocked(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "limit_full.db")
    uid = 101
    settings = _settings(DAILY_GENERATION_LIMIT=5, ADMIN_USER_IDS="")
    for _ in range(5):
        get_storage().increment_generation(uid)
    assert can_consume_generation(uid, settings) is False
    reset_storage_for_tests()


def test_admin_user_over_limit_not_blocked(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "admin_limit.db")
    uid = 999
    settings = _settings(DAILY_GENERATION_LIMIT=5, ADMIN_USER_IDS=str(uid))
    for _ in range(10):
        get_storage().increment_generation(uid)
    assert can_consume_generation(uid, settings) is True
    reset_storage_for_tests()


def test_admin_generations_not_counted() -> None:
    admin_settings = _settings(ADMIN_USER_IDS="42")
    user_settings = _settings(ADMIN_USER_IDS="")
    assert should_increment_daily_count(42, admin_settings) is False
    assert should_increment_daily_count(43, user_settings) is True


def test_is_admin_user_id_matches_settings_admin_ids() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_USER_IDS", "555")
        mp.setenv("BOT_TOKEN", "test-token")
        assert is_admin_user_id(555) is True
        assert is_admin_user_id(1) is False
