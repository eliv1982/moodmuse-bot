"""
Application configuration loaded from environment variables.
"""
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Bot and API settings from env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    BOT_TOKEN: str

    # Logging: DEBUG, INFO, WARNING, ERROR
    LOG_LEVEL: str = "INFO"

    # ProxyAPI.ru (генерация изображений) — универсальный API: openai.api.proxyapi.ru
    PROXI_API_KEY: str = ""
    PROXI_BASE_URL: str = "https://openai.api.proxyapi.ru"

    # GigaChat (text generation)
    # Option 1 (recommended): Authorization key from cabinet (Base64, one string)
    GIGACHAT_AUTHORIZATION_KEY: str = ""
    # Option 2: client_id:client_secret (no spaces/newlines)
    GIGACHAT_CREDENTIALS: str = ""
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    GIGACHAT_API_URL: str = "https://gigachat.devices.sberbank.ru/api/v1"
    GIGACHAT_AUTH_URL: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"


def get_gigachat_credentials(settings: Settings) -> str:
    """
    Возвращает строку для авторизации GigaChat.
    Приоритет: GIGACHAT_AUTHORIZATION_KEY (готовый Base64 из кабинета),
    иначе GIGACHAT_CREDENTIALS (client_id:client_secret). Пробелы и переносы удаляются.
    """
    key = (settings.GIGACHAT_AUTHORIZATION_KEY or "").strip().replace("\r", "").replace("\n", "")
    creds = (settings.GIGACHAT_CREDENTIALS or "").strip().replace("\r", "").replace("\n", "")
    if key:
        return key
    if creds:
        return creds
    logger.warning("GigaChat: ни GIGACHAT_AUTHORIZATION_KEY, ни GIGACHAT_CREDENTIALS не заданы")
    return ""


def get_settings() -> Settings:
    """Return validated settings instance."""
    return Settings()
