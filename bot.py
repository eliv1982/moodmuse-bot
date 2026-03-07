"""
Бот хорошего настроения — открытки с картинкой и подписью к любому празднику (ProxyAPI.ru + GigaChat).
Entry point: polling mode.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import get_settings
from handlers import main_router

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        settings = get_settings()
    except Exception as e:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )
        logging.critical("Ошибка загрузки настроек (.env): %s", e)
        sys.exit(1)
    level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Меньше шума от сторонних библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set")
        sys.exit(1)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(main_router)

    try:
        logger.info("Starting bot (polling)")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
