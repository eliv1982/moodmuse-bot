"""
Admin commands: stats, small talk toggle, maintenance banner, dev profile reset.
"""
import logging

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import get_settings
from handlers.filters import AdminFilter, is_admin_user_id
from handlers.profile import perform_dev_profile_reset
from services.storage import get_storage
from utils.i18n import t

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
        f"• AI idle small talk: {'on' if st_on else 'off'}\n"
        f"• Maintenance: {'on' if maint_on else 'off'}"
    )
    uid = message.from_user.id if message.from_user else None
    logger.info("admin_stats", extra={"user_id": uid, "event": "admin_stats"})


@router.message(Command("smalltalk_on"), AdminFilter())
async def cmd_smalltalk_on(message: Message) -> None:
    get_storage().set_small_talk_enabled(True)
    await message.answer("Idle small talk AI enabled (greetings at home menu).")
    uid = message.from_user.id if message.from_user else None
    logger.info("admin_smalltalk_on", extra={"user_id": uid, "event": "admin_config"})


@router.message(Command("smalltalk_off"), AdminFilter())
async def cmd_smalltalk_off(message: Message) -> None:
    get_storage().set_small_talk_enabled(False)
    await message.answer("Idle small talk AI disabled (template fallback only).")
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


@router.message(Command("dev_reset_me"))
async def cmd_dev_reset_me(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    lang = "en" if get_storage().get_user_lang(uid) == "en" else "ru"
    if not is_admin_user_id(uid):
        await message.answer(t("dev_reset_denied", lang), parse_mode=ParseMode.HTML)
        return
    lang = await perform_dev_profile_reset(uid, state)
    await message.answer(t("dev_reset_done", lang), parse_mode=ParseMode.HTML)
    uid_log = message.from_user.id if message.from_user else None
    logger.info("admin_dev_reset_me", extra={"user_id": uid_log, "event": "admin_dev_reset"})
