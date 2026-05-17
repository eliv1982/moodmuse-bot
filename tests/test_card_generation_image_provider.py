"""card_generation uses image provider factory (mocked)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.card_generation import run_image_only


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "IMAGE_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-key",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_image_only_uses_image_provider() -> None:
    mock_provider = MagicMock()
    mock_provider.generate_image = AsyncMock(return_value=b"\x89PNG")

    with patch(
        "services.card_generation.get_image_provider",
        return_value=mock_provider,
    ):
        image_bytes, prompt = await run_image_only(_settings(), "festive tulips")

    assert image_bytes == b"\x89PNG"
    assert prompt == "festive tulips"
    mock_provider.generate_image.assert_awaited_once_with("festive tulips")
