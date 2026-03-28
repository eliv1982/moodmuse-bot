"""
Register Telegram «Menu» commands (side panel / slash list).
"""
import logging

from aiogram import Bot
from aiogram.types import BotCommand

logger = logging.getLogger(__name__)


async def setup_bot_commands(bot: Bot) -> None:
    """RU/EN descriptions + default list for clients without locale match."""
    ru = [
        BotCommand(command="start", description="Создать открытку"),
        BotCommand(command="cancel", description="Отменить сценарий"),
        BotCommand(command="lang", description="Язык интерфейса"),
        BotCommand(command="help", description="Справка и команды"),
    ]
    en = [
        BotCommand(command="start", description="Create a greeting card"),
        BotCommand(command="cancel", description="Cancel the wizard"),
        BotCommand(command="lang", description="Interface language"),
        BotCommand(command="help", description="Help and commands"),
    ]
    try:
        await bot.set_my_commands(ru, language_code="ru")
        await bot.set_my_commands(en, language_code="en")
        await bot.set_my_commands(ru)
        logger.info("bot_commands_registered", extra={"event": "startup"})
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e, extra={"event": "startup"})
