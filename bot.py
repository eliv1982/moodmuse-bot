"""
Telegram bot: greeting cards (ProxyAPI images + YandexGPT text). Polling entrypoint.
"""
import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import get_settings
from handlers import admin_router, main_router
from handlers.middlewares import MaintenanceMiddleware
from services.storage import init_storage
from utils.bot_commands import setup_bot_commands
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


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

    if not (settings.YANDEX_API_KEY or "").strip() or not (settings.YANDEX_FOLDER_ID or "").strip():
        logger.warning(
            "Yandex Cloud not configured: set YANDEX_API_KEY and YANDEX_FOLDER_ID "
            "(e.g. in .env next to docker-compose, then recreate container). "
            "Captions and prompt refinement will fail until then.",
            extra={"event": "startup", "component": "yandex"},
        )

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
    dp.include_router(main_router)

    try:
        await setup_bot_commands(bot)
        logger.info("polling_start", extra={"event": "startup"})
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
