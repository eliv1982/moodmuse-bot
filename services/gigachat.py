"""
GigaChat (Sber) API client for greeting text generation.
Uses OAuth with client_id:client_secret and chat completions endpoint.
Supports both "client_id:client_secret" and pre-encoded Base64 key from cabinet.
"""
import base64
import json
import logging
import re
import uuid
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

GIGACHAT_CHAT_MODEL = "GigaChat:latest"

# Base64 alphabet (no padding) — to detect if credentials are already encoded
_B64_PATTERN = re.compile(r"^[A-Za-z0-9+/]+=*$")


class GigaChatError(Exception):
    """GigaChat API error."""

    pass


def _normalize_credentials(credentials: str) -> str:
    """
    Strip whitespace, newlines, BOM; remove accidental 'Basic ' prefix.
    Оставляем только символы, допустимые в Base64 или в client_id:client_secret (латиница, цифры, дефис, двоеточие).
    """
    s = (credentials or "").strip().replace("\r", "").replace("\n", "").replace("\t", "")
    if s.startswith("\ufeff"):
        s = s[1:]  # BOM
    if s.upper().startswith("BASIC "):
        s = s[6:].strip()
    # Убираем возможный мусор по краям (пробелы после нормализации)
    return s.strip()


def _get_auth_header(credentials: str) -> str:
    """
    Build 'Authorization: Basic <key>' for GigaChat OAuth.
    - Key from cabinet (one Base64 string, no colon) → use as-is after 'Basic '.
    - client_id:client_secret → encode to Base64, then 'Basic ' + result.
    """
    raw = _normalize_credentials(credentials)
    if not raw:
        logger.error("GigaChat: credentials empty. Set GIGACHAT_CREDENTIALS or GIGACHAT_AUTHORIZATION_KEY in .env")
        raise GigaChatError(
            "Не заданы учётные данные GigaChat. Укажите в .env GIGACHAT_CREDENTIALS (client_id:client_secret) "
            "или GIGACHAT_AUTHORIZATION_KEY (ключ из кабинета Сбера)."
        )

    # Готовый ключ из кабинета: одна строка Base64 (без двоеточия)
    if ":" not in raw:
        if _B64_PATTERN.match(raw):
            logger.info("GigaChat: using pre-encoded Authorization key from cabinet (len=%d)", len(raw))
            return "Basic " + raw
        logger.warning("GigaChat: value has no ':' and doesn't look like Base64; will encode as-is")

    # client_id:client_secret — кодируем в Base64 (как в документации Сбера)
    try:
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    except Exception as e:
        logger.exception("GigaChat: failed to encode credentials")
        raise GigaChatError(f"Invalid credentials encoding: {e}") from e
    if not _B64_PATTERN.match(encoded):
        logger.warning("GigaChat: encoded result doesn't look like valid Base64")
    logger.info("GigaChat: using client_id:client_secret (encoded len=%d)", len(encoded))
    return "Basic " + encoded


async def _get_access_token(
    credentials: str,
    scope: str,
    auth_url: str,
    timeout: float = 30.0,
) -> str:
    """Obtain GigaChat access token via OAuth."""
    logger.info("GigaChat: requesting access token (scope=%s)", scope)
    auth_value = _get_auth_header(credentials)
    # Для отладки 400: проверяем формат (без вывода секрета)
    if logger.isEnabledFor(logging.DEBUG):
        sample = auth_value[:15] + "..." if len(auth_value) > 15 else auth_value
        logger.debug("GigaChat: Authorization header len=%d, starts with: %s", len(auth_value), sample)

    headers = {
        "Authorization": auth_value,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
    }
    data = {"scope": scope}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                auth_url,
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=True,
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "GigaChat auth failed: status=%s, body=%s",
                        resp.status,
                        body[:500],
                    )
                    raise GigaChatError(f"Auth failed {resp.status}: {body[:300]}")

                result = json.loads(body)
                token = result.get("access_token")
                if not token:
                    logger.error("GigaChat auth: no access_token in response keys=%s", list(result.keys()))
                    raise GigaChatError("No access_token in auth response")
                logger.info("GigaChat: access token received successfully")
                return token
    except aiohttp.ClientError as e:
        logger.exception("GigaChat auth request failed: %s", e)
        raise GigaChatError(f"Auth request failed: {e}") from e


async def generate_greeting_text(
    system_prompt: str,
    user_prompt: str,
    *,
    credentials: str,
    scope: str,
    api_url: str,
    auth_url: str,
    model: str = GIGACHAT_CHAT_MODEL,
    timeout: float = 60.0,
) -> str:
    """
    Generate greeting text using GigaChat chat completions.
    Returns the assistant message content.
    """
    logger.info("GigaChat: generating greeting text (model=%s)", model)
    token = await _get_access_token(credentials, scope, auth_url, timeout=timeout)

    url = api_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    logger.debug("GigaChat: POST %s", url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=True,
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "GigaChat chat failed: status=%s, body=%s",
                        resp.status,
                        text[:500],
                    )
                    raise GigaChatError(f"Chat API returned {resp.status}: {text[:500]}")

                result = json.loads(text)
    except aiohttp.ClientError as e:
        logger.exception("GigaChat chat request failed: %s", e)
        raise GigaChatError(f"Request failed: {e}") from e

    choices = result.get("choices")
    if not choices or not isinstance(choices, list):
        logger.error("GigaChat: response has no choices, keys=%s", list(result.keys()) if isinstance(result, dict) else type(result))
        raise GigaChatError("GigaChat response has no 'choices'")

    message = choices[0].get("message") or {}
    content = message.get("content") or message.get("text")
    if content is None:
        logger.error("GigaChat: no message content in choice, message=%s", message)
        raise GigaChatError("GigaChat response has no message content")

    logger.info("GigaChat: greeting generated, length=%d", len(content))
    return content.strip()


# System prompt for small talk: always remind about the bot's purpose
SMALL_TALK_SYSTEM = (
    "Ты — бот весеннего настроения. Твоя главная задача — помогать создавать "
    "персонализированные поздравительные открытки (картинка + текст). "
    "В каждом ответе мягко и коротко напомни, что пользователь может создать открытку — для этого нужно отправить команду /start. "
    "Отвечай на реплику пользователя кратко (1–2 предложения), дружелюбно и по делу. Не пиши длинных абзацев."
)


async def small_talk_reply(
    user_message: str,
    *,
    credentials: str,
    scope: str,
    api_url: str,
    auth_url: str,
    timeout: float = 30.0,
) -> str:
    """
    Generate a short friendly reply for small talk, reminding about creating cards.
    """
    logger.debug("GigaChat: small talk request (len=%d)", len(user_message or ""))
    return await generate_greeting_text(
        SMALL_TALK_SYSTEM,
        user_message or "Привет",
        credentials=credentials,
        scope=scope,
        api_url=api_url,
        auth_url=auth_url,
        model=GIGACHAT_CHAT_MODEL,
        timeout=timeout,
    )
