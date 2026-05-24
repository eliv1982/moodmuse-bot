"""
Telegram bot: greeting cards (ProxyAPI images + YandexGPT text). Polling entrypoint.

TODO(observability): ship structured logs to Grafana Loki in a follow-up task (not this branch).
"""
import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Settings, get_settings
from services.providers.stt_factory import normalize_stt_provider_name
from handlers import admin_router, main_router, profile_router
from handlers.middlewares import MaintenanceMiddleware
from services.storage import init_storage
from utils.bot_commands import setup_bot_commands
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _log_startup_provider_warnings(settings: Settings) -> None:
    """Provider-aware configuration warnings (no secrets in logs)."""
    text_provider = (settings.TEXT_PROVIDER or "yandex").strip().lower()
    image_provider = (settings.IMAGE_PROVIDER or "proxi").strip().lower()
    openai_key = (settings.OPENAI_API_KEY or "").strip()
    yandex_ok = bool((settings.YANDEX_API_KEY or "").strip() and (settings.YANDEX_FOLDER_ID or "").strip())
    proxi_key = (settings.PROXI_API_KEY or "").strip()
    proxi_base = (settings.PROXI_BASE_URL or "").strip()

    if text_provider == "yandex":
        if not yandex_ok:
            logger.warning(
                "Yandex text not configured: set YANDEX_API_KEY and YANDEX_FOLDER_ID "
                "(TEXT_PROVIDER=yandex). Captions and prompt refinement will fail until then.",
                extra={"event": "startup", "component": "yandex"},
            )
    elif text_provider == "openai":
        if not openai_key:
            logger.warning(
                "OpenAI text not configured: set OPENAI_API_KEY (TEXT_PROVIDER=openai).",
                extra={"event": "startup", "component": "openai_text"},
            )
    else:
        logger.warning(
            "Unknown TEXT_PROVIDER=%r — text generation may fail.",
            settings.TEXT_PROVIDER,
            extra={"event": "startup", "component": "text_provider"},
        )

    if image_provider == "proxi":
        if not proxi_key:
            logger.warning(
                "ProxyAPI image not configured: set PROXI_API_KEY (IMAGE_PROVIDER=proxi).",
                extra={"event": "startup", "component": "proxi_image"},
            )
    elif image_provider == "openai":
        if not openai_key:
            logger.warning(
                "OpenAI image not configured: set OPENAI_API_KEY (IMAGE_PROVIDER=openai).",
                extra={"event": "startup", "component": "openai_image"},
            )
    else:
        logger.warning(
            "Unknown IMAGE_PROVIDER=%r — image generation may fail.",
            settings.IMAGE_PROVIDER,
            extra={"event": "startup", "component": "image_provider"},
        )

    stt_provider = normalize_stt_provider_name(settings.STT_PROVIDER)
    if stt_provider == "openai":
        if not openai_key:
            logger.warning(
                "Voice input unavailable: set OPENAI_API_KEY (STT_PROVIDER=openai).",
                extra={"event": "startup", "component": "stt"},
            )
    elif stt_provider == "proxiapi":
        if not proxi_key or not proxi_base:
            logger.warning(
                "Voice input unavailable: set PROXI_API_KEY and PROXI_BASE_URL "
                "(STT_PROVIDER=proxi or STT_PROVIDER=proxiapi).",
                extra={"event": "startup", "component": "stt"},
            )
    else:
        logger.warning(
            "Unknown STT_PROVIDER=%r — voice input may fail.",
            settings.STT_PROVIDER,
            extra={"event": "startup", "component": "stt"},
        )


async def main() -> None:
    try:
        settings = get_settings()
    except Exception as e:
        setup_logging(logging.INFO, json_format=False)
        logging.critical("Settings load failed (.env): %s", e)
        sys.exit(1)

    level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)
    setup_logging(level, json_format=bool(settings.LOG_JSON))

    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set")
        sys.exit(1)

    _log_startup_provider_warnings(settings)

    db_path = Path(settings.DATA_DIR) / "bot.db"
    init_storage(db_path)
    logger.info("storage_ready", extra={"event": "startup"})

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware(MaintenanceMiddleware())
    dp.include_router(admin_router)
    dp.include_router(profile_router)
    dp.include_router(main_router)

    try:
        await setup_bot_commands(bot)
        logger.info("polling_start", extra={"event": "startup"})
        try:
            await dp.start_polling(bot)
        except asyncio.CancelledError:
            logger.info("Bot stopped by user", extra={"event": "shutdown"})
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Bot stopped by user", extra={"event": "shutdown"})
