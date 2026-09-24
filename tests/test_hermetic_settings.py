"""The suite runs on fake config only: no .env and no ambient provider credentials."""
from __future__ import annotations

from config import Settings, get_settings


def test_get_settings_needs_only_fake_bot_token() -> None:
    s = get_settings()
    assert s.BOT_TOKEN == "test-token"
    assert Settings.model_config["env_file"] is None


def test_get_settings_has_no_provider_credentials() -> None:
    s = get_settings()
    assert s.PROXI_API_KEY == ""
    assert s.OPENAI_API_KEY == ""
    assert s.YANDEX_API_KEY == ""
    assert s.YANDEX_FOLDER_ID == ""
    assert s.admin_ids() == []
