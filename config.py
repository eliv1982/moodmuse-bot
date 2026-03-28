"""
Application configuration loaded from environment variables.
"""
import logging
import os
from pathlib import Path
from typing import List, Self

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Загрузка .env до чтения Settings: локально — из каталога проекта; в Docker — часто /app/.env при монтировании.
# override=False: переменные, уже заданные Docker Compose / ОС, не перезаписываются.
_APP_DIR = Path(__file__).resolve().parent
for _env_path in (_APP_DIR / ".env", Path("/app/.env")):
    try:
        load_dotenv(_env_path, override=False)
    except OSError:
        pass


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
    # If false, use plain text log lines (dev)
    LOG_JSON: bool = True

    # Data directory (SQLite)
    DATA_DIR: Path = Path("data")

    # Limits
    DAILY_GENERATION_LIMIT: int = 5

    # Telegram caption (HTML) max length
    MAX_CAPTION_LENGTH: int = 1024

    # Admin Telegram user IDs (comma-separated)
    ADMIN_USER_IDS: str = ""

    # ProxyAPI.ru (images + STT)
    PROXI_API_KEY: str = ""
    PROXI_BASE_URL: str = "https://openai.api.proxyapi.ru"

    # Yandex Cloud Foundation Models (text + prompt refine)
    YANDEX_API_KEY: str = ""
    YANDEX_FOLDER_ID: str = ""
    # e.g. yandexgpt/latest or yandexgpt-lite/latest
    YANDEX_MODEL_SUFFIX: str = "yandexgpt/latest"
    YANDEX_COMPLETION_URL: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    YANDEX_TIMEOUT: float = 90.0
    YANDEX_PROMPT_REFINE_TIMEOUT: float = 45.0

    # Image generation
    PROXI_IMAGE_TIMEOUT: float = 120.0
    PROXI_IMAGE_MODEL: str = "gpt-image-1"

    # Speech-to-text
    STT_TIMEOUT: float = 45.0

    @field_validator("DATA_DIR", mode="before")
    @classmethod
    def parse_data_dir(cls, v: object) -> Path:
        if isinstance(v, Path):
            return v
        return Path(str(v))

    @field_validator("YANDEX_API_KEY", "YANDEX_FOLDER_ID", "PROXI_API_KEY", mode="before")
    @classmethod
    def strip_secret_whitespace(cls, v: object) -> object:
        if v is None:
            return ""
        s = str(v).strip()
        if s.startswith("\ufeff"):
            s = s[1:]
        return s

    @model_validator(mode="after")
    def merge_yandex_from_os_environ(self) -> Self:
        """
        Редко pydantic-settings не подхватывает переменные из окружения контейнера.
        Дублируем из os.environ, если в модели пусто, а в процессе переменные есть.
        """
        key = (self.YANDEX_API_KEY or "").strip()
        folder = (self.YANDEX_FOLDER_ID or "").strip()
        ek = os.environ.get("YANDEX_API_KEY", "").strip()
        ef = os.environ.get("YANDEX_FOLDER_ID", "").strip()
        if not key and ek:
            key = ek
        if not folder and ef:
            folder = ef
        if key != self.YANDEX_API_KEY or folder != self.YANDEX_FOLDER_ID:
            return self.model_copy(update={"YANDEX_API_KEY": key, "YANDEX_FOLDER_ID": folder})
        return self

    def model_uri(self) -> str:
        fid = (self.YANDEX_FOLDER_ID or "").strip()
        suf = (self.YANDEX_MODEL_SUFFIX or "yandexgpt/latest").strip().lstrip("/")
        return f"gpt://{fid}/{suf}"

    def admin_ids(self) -> List[int]:
        raw = (self.ADMIN_USER_IDS or "").strip()
        if not raw:
            return []
        out: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except ValueError:
                logger.warning("Invalid ADMIN_USER_IDS entry ignored: %s", part)
        return out


def get_settings() -> Settings:
    """Return validated settings instance."""
    return Settings()
