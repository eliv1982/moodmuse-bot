"""OpenAI text provider with mocked aiohttp (no network)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.providers.openai_text import OpenAITextError, OpenAITextProvider


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "TEXT_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _mock_session_response(body: dict, *, status: int = 200) -> tuple[MagicMock, MagicMock]:
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
    return session, post_cm


@pytest.mark.asyncio
async def test_generate_greeting_text_success() -> None:
    provider = OpenAITextProvider(_settings())
    session, _ = _mock_session_response(
        {"choices": [{"message": {"content": " Happy birthday! "}}]}
    )

    with patch(
        "services.providers.openai_text.aiohttp.ClientSession",
        return_value=session,
    ):
        result = await provider.generate_greeting_text(
            "system",
            "user",
            timeout=30.0,
            max_tokens=100,
            temperature=0.5,
        )

    assert result == "Happy birthday!"
    call_kwargs = session.post.call_args.kwargs
    assert call_kwargs["json"]["model"] == "gpt-4o-mini"
    assert call_kwargs["json"]["messages"][0]["role"] == "system"
    assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_chat_completions_url_default() -> None:
    provider = OpenAITextProvider(_settings())
    assert provider._chat_completions_url() == "https://api.openai.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_chat_completions_url_with_v1_suffix() -> None:
    provider = OpenAITextProvider(
        _settings(OPENAI_BASE_URL="https://api.openai.com/v1")
    )
    assert provider._chat_completions_url() == "https://api.openai.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_missing_api_key_raises() -> None:
    provider = OpenAITextProvider(_settings(OPENAI_API_KEY=""))
    with pytest.raises(OpenAITextError, match="OPENAI_API_KEY"):
        await provider.generate_greeting_text("s", "u", timeout=10.0)


@pytest.mark.asyncio
async def test_http_error_raises() -> None:
    provider = OpenAITextProvider(_settings())
    session, _ = _mock_session_response({"error": "bad"}, status=401)

    with patch(
        "services.providers.openai_text.aiohttp.ClientSession",
        return_value=session,
    ):
        with pytest.raises(OpenAITextError, match="OpenAI API 401"):
            await provider.generate_greeting_text("s", "u", timeout=10.0)


@pytest.mark.asyncio
async def test_empty_choices_raises() -> None:
    provider = OpenAITextProvider(_settings())
    session, _ = _mock_session_response({"choices": []})

    with patch(
        "services.providers.openai_text.aiohttp.ClientSession",
        return_value=session,
    ):
        with pytest.raises(OpenAITextError, match="no choices"):
            await provider.generate_greeting_text("s", "u", timeout=10.0)


@pytest.mark.asyncio
async def test_enhance_image_prompt_truncates_long_line() -> None:
    provider = OpenAITextProvider(_settings())
    long_text = "x" * 950
    session, _ = _mock_session_response(
        {"choices": [{"message": {"content": long_text}}]}
    )

    with patch(
        "services.providers.openai_text.aiohttp.ClientSession",
        return_value=session,
    ):
        result = await provider.enhance_image_prompt(
            draft_english_prompt="draft",
            lang="en",
            timeout=10.0,
        )

    assert len(result) == 900
    assert result.endswith("...")
