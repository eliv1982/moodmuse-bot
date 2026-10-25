"""ALLOWED_USER_IDS parsing: explicit ids only, everything else fails closed."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import bot as bot_module
from config import Settings, get_settings

ROOT = Path(__file__).resolve().parent.parent


def _settings(**kwargs: object) -> Settings:
    return Settings(BOT_TOKEN="test-token", **kwargs)  # type: ignore[arg-type]


def test_missing_allowlist_fails_closed() -> None:
    # conftest scrubs the environment, so this is the "variable not set at all" case.
    assert get_settings().allowed_user_ids() == frozenset()


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_allowlist_fails_closed(raw: str) -> None:
    assert _settings(ALLOWED_USER_IDS=raw).allowed_user_ids() == frozenset()


@pytest.mark.parametrize(
    "raw",
    [
        "123,",  # trailing comma
        ",123",  # leading comma
        "123,,456",  # consecutive commas
        "123, ,456",  # whitespace-only element
        "123,\t,456",
        "123,   ",  # trailing whitespace-only element
        "  ,123",  # leading whitespace-only element
        "123,456,",
        ",123,456",
        "123,,",
        ",,123",
        "123,456,,789",
        ",",  # nothing but empty elements
        " , ,, ",
        ",,",
    ],
)
def test_empty_allowlist_element_rejects_whole_list(raw: str) -> None:
    # Every id in these lists is valid; the empty element alone must make the list authorize nobody.
    assert _settings(ALLOWED_USER_IDS=raw).allowed_user_ids() == frozenset()


def test_empty_allowlist_element_logs_position_not_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="config")
    _settings(ALLOWED_USER_IDS="111222333,,444555666").allowed_user_ids()
    assert "#2" in caplog.text
    assert "every user is denied" in caplog.text
    for value in ("111222333", "444555666"):
        assert value not in caplog.text


@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "123,abc",  # one bad entry rejects the whole list, not just itself
        "abc,123",
        "123 456",  # whitespace-separated is not a list
        "123;456",
        "-5",  # negative ids are chats, not users
        "0",
        "+5",
        "1_000",  # int() would accept this
        "12.5",
        "0123",
        "٣٣",  # non-ASCII digits, int() would accept these
        "<owner_telegram_id>",
        "*",
        "all",
    ],
)
def test_malformed_allowlist_fails_closed(raw: str) -> None:
    assert _settings(ALLOWED_USER_IDS=raw).allowed_user_ids() == frozenset()


def test_valid_allowlist_is_parsed_exactly() -> None:
    # Whitespace around an element is fine; an empty element is not (see above). Duplicates collapse.
    s = _settings(ALLOWED_USER_IDS="123, 456 ,789,123")
    assert s.allowed_user_ids() == frozenset({123, 456, 789})


def test_single_id_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_USER_IDS", "424242")
    assert get_settings().allowed_user_ids() == frozenset({424242})


def test_admin_ids_are_not_implicitly_allowed() -> None:
    s = _settings(ADMIN_USER_IDS="555,666", ALLOWED_USER_IDS="777")
    assert s.allowed_user_ids() == frozenset({777})
    assert not set(s.admin_ids()) & s.allowed_user_ids()


def test_admin_ids_alone_allow_nobody() -> None:
    s = _settings(ADMIN_USER_IDS="555,666")
    assert s.allowed_user_ids() == frozenset()


def test_rejected_allowlist_logs_position_not_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="config")
    _settings(ALLOWED_USER_IDS="111222333,not-an-id-secret,444555666").allowed_user_ids()
    assert "#2" in caplog.text
    for value in ("111222333", "not-an-id-secret", "444555666"):
        assert value not in caplog.text


def test_valid_allowlist_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="config")
    _settings(ALLOWED_USER_IDS="111222333,444555666").allowed_user_ids()
    assert "111222333" not in caplog.text
    assert "444555666" not in caplog.text


def test_env_example_never_grants_access_even_when_uncommented() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    entries = [ln for ln in lines if ln.lstrip("# ").startswith("ALLOWED_USER_IDS=")]
    assert entries, ".env.example should document ALLOWED_USER_IDS"
    for line in entries:
        value = line.lstrip("# ").split("=", 1)[1]
        assert _settings(ALLOWED_USER_IDS=value).allowed_user_ids() == frozenset()


def test_startup_reports_closed_access_as_error(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="bot")
    bot_module._log_startup_access(frozenset())
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
    assert "every user will be denied" in caplog.text


def test_startup_reports_allowlist_size_never_the_ids(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="bot")
    bot_module._log_startup_access(frozenset({111222333, 444555666}))
    assert "users=2" in caplog.text
    assert "111222333" not in caplog.text
    assert "444555666" not in caplog.text
