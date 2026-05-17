"""OpenAI image provider with mocked aiohttp (no network)."""
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.providers.openai_image import OpenAIImageError, OpenAIImageProvider


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "IMAGE_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_IMAGE_MODEL": "gpt-image-1",
        "OPENAI_IMAGE_SIZE": "1024x1024",
        "OPENAI_IMAGE_TIMEOUT": 60.0,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _mock_post_response(body: dict, *, status: int = 200) -> MagicMock:
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value=json.dumps(body))

    post_cm = AsyncMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_generate_image_b64_json() -> None:
    raw = b"fake-png-bytes"
    b64 = base64.b64encode(raw).decode("ascii")
    provider = OpenAIImageProvider(_settings())
    session = _mock_post_response({"data": [{"b64_json": b64}]})

    with patch(
        "services.providers.openai_image.aiohttp.ClientSession",
        return_value=session,
    ):
        out = await provider.generate_image("a festive card")

    assert out == raw
    payload = session.post.call_args.kwargs["json"]
    assert payload["model"] == "gpt-image-1"
    assert payload["size"] == "1024x1024"
    assert payload["n"] == 1
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_images_generations_url() -> None:
    provider = OpenAIImageProvider(_settings())
    assert (
        provider._images_generations_url()
        == "https://api.openai.com/v1/images/generations"
    )


@pytest.mark.asyncio
async def test_missing_api_key_raises() -> None:
    provider = OpenAIImageProvider(_settings(OPENAI_API_KEY=""))
    with pytest.raises(OpenAIImageError, match="OPENAI_API_KEY"):
        await provider.generate_image("prompt")


@pytest.mark.asyncio
async def test_http_error_raises() -> None:
    provider = OpenAIImageProvider(_settings())
    session = _mock_post_response({"error": "bad"}, status=403)

    with patch(
        "services.providers.openai_image.aiohttp.ClientSession",
        return_value=session,
    ):
        with pytest.raises(OpenAIImageError, match="OpenAI API 403"):
            await provider.generate_image("prompt")


@pytest.mark.asyncio
async def test_empty_data_raises() -> None:
    provider = OpenAIImageProvider(_settings())
    session = _mock_post_response({"data": []})

    with patch(
        "services.providers.openai_image.aiohttp.ClientSession",
        return_value=session,
    ):
        with pytest.raises(OpenAIImageError, match="no data"):
            await provider.generate_image("prompt")


@pytest.mark.asyncio
async def test_url_response_downloads_image() -> None:
    provider = OpenAIImageProvider(_settings())
    post_session = _mock_post_response(
        {"data": [{"url": "https://example.com/img.png"}]}
    )

    get_resp = AsyncMock()
    get_resp.status = 200
    get_resp.read = AsyncMock(return_value=b"downloaded")

    get_cm = AsyncMock()
    get_cm.__aenter__ = AsyncMock(return_value=get_resp)
    get_cm.__aexit__ = AsyncMock(return_value=None)

    get_session = MagicMock()
    get_session.get = MagicMock(return_value=get_cm)
    get_session.__aenter__ = AsyncMock(return_value=get_session)
    get_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "services.providers.openai_image.aiohttp.ClientSession",
        side_effect=[post_session, get_session],
    ):
        out = await provider.generate_image("prompt")

    assert out == b"downloaded"
