"""
Admin commands: stats, small talk toggle, maintenance banner.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import get_settings
from handlers.filters import AdminFilter
from services.storage import get_storage

logger = logging.getLogger(__name__)

router = Router(name="admin")


@router.message(Command("stats"), AdminFilter())
async def cmd_stats(message: Message) -> None:
    storage = get_storage()
    total_today, unique_today = storage.stats_today()
    total_all = storage.stats_total()
    st_on = storage.is_small_talk_enabled()
    maint_on = bool(storage.get_maintenance_message().strip())
    limit = get_settings().DAILY_GENERATION_LIMIT
    await message.answer(
        "Admin stats (UTC day):\n"
        f"• Generations today: {total_today}\n"
        f"• Unique users today: {unique_today}\n"
        f"• Total generations (log): {total_all}\n"
        f"• Daily user limit: {limit}\n"
        f"• Small talk LLM: {'on' if st_on else 'off'}\n"
        f"• Maintenance: {'on' if maint_on else 'off'}"
    )
    uid = message.from_user.id if message.from_user else None
    logger.info("admin_stats", extra={"user_id": uid, "event": "admin_stats"})


@router.message(Command("smalltalk_on"), AdminFilter())
async def cmd_smalltalk_on(message: Message) -> None:
    get_storage().set_small_talk_enabled(True)
    await message.answer("Small talk LLM enabled.")
    uid = message.from_user.id if message.from_user else None
    logger.info("admin_smalltalk_on", extra={"user_id": uid, "event": "admin_config"})


@router.message(Command("smalltalk_off"), AdminFilter())
async def cmd_smalltalk_off(message: Message) -> None:
    get_storage().set_small_talk_enabled(False)
    await message.answer("Small talk LLM disabled (fallback text only).")
    uid = message.from_user.id if message.from_user else None
    logger.info("admin_smalltalk_off", extra={"user_id": uid, "event": "admin_config"})


@router.message(Command("maintenance"), AdminFilter())
async def cmd_maintenance(message: Message) -> None:
    text = message.text or ""
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    storage = get_storage()
    if not arg or arg.lower() in ("off", "false", "0", "none", "clear"):
        storage.set_maintenance_message("")
        await message.answer("Maintenance cleared. Bot is open for users.")
    else:
        storage.set_maintenance_message(arg)
        await message.answer("Maintenance message set. Non-admins will see it on each update.")
    uid = message.from_user.id if message.from_user else None
    logger.info("admin_maintenance", extra={"user_id": uid, "event": "admin_config"})
