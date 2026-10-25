"""Image model migration: new defaults, request payload, timeout and explicit overrides (no network)."""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.providers.image_factory import get_image_provider, image_provider_configured
from services.providers.factory import get_text_provider, text_provider_configured
from services.providers.openai_image import OpenAIImageProvider
from services.providers.openai_text import OpenAITextProvider
from services.providers.proxi_image import ProxiImageProvider
from services.providers.yandex_text import YandexTextProvider

NEW_MODEL = "gpt-image-2.5-flare"
RETIRED_MODEL = "gpt-image-1"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"BOT_TOKEN": "test-token", "_env_file": None}
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _session_returning(body: dict) -> MagicMock:
    resp = AsyncMock()
    resp.status = 200
    resp.text = AsyncMock(return_value=json.dumps(body))
    post_cm = AsyncMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


async def _generate(settings: Settings, body: dict | None = None) -> tuple[MagicMock, bytes]:
    """Run one generation against a fake HTTP session; return (session, image bytes)."""
    b64 = base64.b64encode(b"PNG-BYTES").decode("ascii")
    session = _session_returning(body or {"data": [{"b64_json": b64}]})
    with patch("services.providers.openai_image.aiohttp.ClientSession", return_value=session):
        out = await OpenAIImageProvider(settings).generate_image("a festive card")
    return session, out


# ----- defaults -----


def test_default_image_model_is_the_new_one_and_not_the_retired_one() -> None:
    s = _settings()
    assert s.OPENAI_IMAGE_MODEL == NEW_MODEL
    assert s.PROXI_IMAGE_MODEL == NEW_MODEL
    assert RETIRED_MODEL not in (s.OPENAI_IMAGE_MODEL, s.PROXI_IMAGE_MODEL)


def test_default_quality_and_timeout() -> None:
    s = _settings()
    assert s.OPENAI_IMAGE_QUALITY == "medium"
    assert s.OPENAI_IMAGE_TIMEOUT == 180.0
    assert s.OPENAI_IMAGE_SIZE == "1024x1024"


def test_direct_openai_is_the_default_for_images_and_text() -> None:
    s = _settings(OPENAI_API_KEY="sk-test")
    assert s.IMAGE_PROVIDER == "openai"
    assert s.TEXT_PROVIDER == "openai"
    assert isinstance(get_image_provider(s), OpenAIImageProvider)
    assert isinstance(get_text_provider(s), OpenAITextProvider)
    assert image_provider_configured(s)
    assert text_provider_configured(s)


def test_default_routes_need_no_legacy_credentials() -> None:
    s = _settings(OPENAI_API_KEY="sk-test", PROXI_API_KEY="", YANDEX_API_KEY="", YANDEX_FOLDER_ID="")
    assert image_provider_configured(s)
    assert text_provider_configured(s)


def test_empty_provider_names_fall_back_to_openai() -> None:
    s = _settings(IMAGE_PROVIDER="", TEXT_PROVIDER="", OPENAI_API_KEY="sk-test")
    assert isinstance(get_image_provider(s), OpenAIImageProvider)
    assert isinstance(get_text_provider(s), OpenAITextProvider)
    assert image_provider_configured(s)
    assert text_provider_configured(s)


def test_quality_and_model_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "high")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")
    monkeypatch.setenv("OPENAI_IMAGE_TIMEOUT", "240")
    s = Settings(BOT_TOKEN="test-token", _env_file=None)  # type: ignore[call-arg]
    assert (s.OPENAI_IMAGE_QUALITY, s.OPENAI_IMAGE_MODEL, s.OPENAI_IMAGE_TIMEOUT) == (
        "high",
        "gpt-image-2.5-sunburst",
        240.0,
    )


# ----- explicit overrides of the old routes keep working -----


def test_legacy_providers_remain_selectable() -> None:
    assert isinstance(get_image_provider(_settings(IMAGE_PROVIDER="proxi")), ProxiImageProvider)
    assert isinstance(get_text_provider(_settings(TEXT_PROVIDER="yandex")), YandexTextProvider)


def test_legacy_provider_credentials_still_gate_their_routes() -> None:
    assert image_provider_configured(_settings(IMAGE_PROVIDER="proxi", PROXI_API_KEY="pk"))
    assert not image_provider_configured(_settings(IMAGE_PROVIDER="proxi", PROXI_API_KEY=""))


@pytest.mark.asyncio
async def test_explicit_model_override_is_sent_unchanged() -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk", OPENAI_IMAGE_MODEL=RETIRED_MODEL))
    assert session.post.call_args.kwargs["json"]["model"] == RETIRED_MODEL


@pytest.mark.asyncio
async def test_proxi_route_sends_configured_model_and_no_quality() -> None:
    sent: dict[str, object] = {}

    async def fake_generate(prompt: str, **kwargs: object) -> bytes:
        sent.update(kwargs)
        return b"img"

    provider = ProxiImageProvider(_settings(IMAGE_PROVIDER="proxi", PROXI_API_KEY="pk"))
    with patch("services.providers.proxi_image.generate_image", side_effect=fake_generate):
        assert await provider.generate_image("p") == b"img"
    assert sent["model"] == NEW_MODEL
    assert "quality" not in sent


# ----- direct OpenAI request -----


@pytest.mark.asyncio
async def test_payload_has_new_model_quality_size_and_count() -> None:
    session, out = await _generate(_settings(OPENAI_API_KEY="sk-test"))

    assert out == b"PNG-BYTES"
    payload = session.post.call_args.kwargs["json"]
    assert payload == {
        "model": NEW_MODEL,
        "prompt": "a festive card",
        "size": "1024x1024",
        "n": 1,
        "quality": "medium",
    }
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_request_goes_to_the_images_generations_endpoint() -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk-test"))
    assert session.post.call_args.args[0] == "https://api.openai.com/v1/images/generations"


@pytest.mark.asyncio
async def test_request_timeout_is_180_seconds_by_default() -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk-test"))
    assert session.post.call_args.kwargs["timeout"].total == 180.0


@pytest.mark.asyncio
async def test_request_timeout_override_is_respected() -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk-test", OPENAI_IMAGE_TIMEOUT=45.0))
    assert session.post.call_args.kwargs["timeout"].total == 45.0


@pytest.mark.asyncio
@pytest.mark.parametrize("quality", ["low", "high", "auto"])
async def test_quality_override_is_sent(quality: str) -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk", OPENAI_IMAGE_QUALITY=quality))
    assert session.post.call_args.kwargs["json"]["quality"] == quality


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "  "])
async def test_blank_quality_omits_the_parameter(blank: str) -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk", OPENAI_IMAGE_QUALITY=blank))
    assert "quality" not in session.post.call_args.kwargs["json"]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["dall-e-3", "dall-e-2"])
async def test_quality_is_not_sent_to_models_that_do_not_take_it(model: str) -> None:
    session, _ = await _generate(_settings(OPENAI_API_KEY="sk", OPENAI_IMAGE_MODEL=model))
    payload = session.post.call_args.kwargs["json"]
    assert payload["model"] == model
    assert "quality" not in payload


@pytest.mark.asyncio
async def test_base64_response_is_decoded() -> None:
    raw = bytes(range(256)) * 4
    _, out = await _generate(
        _settings(OPENAI_API_KEY="sk"),
        {"data": [{"b64_json": base64.b64encode(raw).decode("ascii")}]},
    )
    assert out == raw
