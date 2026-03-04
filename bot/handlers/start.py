from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from bot.keyboards.inline import main_menu_kb, paywall_kb
from db.database import fetch_one
from services.user_manager import get_or_create_user, start_trial, check_entitlement

router = Router()

WELCOME_TEXT = (
    "🤖 <b>TelegramSMM</b>\n\n"
    "Бот для автоматизации SMM-кампаний в Telegram.\n\n"
    "Выберите раздел:"
)


async def _is_admin(user_id: int) -> bool:
    from core.config import SUPERADMIN_IDS
    if user_id in SUPERADMIN_IDS:
        return True
    admin = await fetch_one(
        "SELECT 1 FROM admins WHERE user_id = ? AND is_active = 1",
        (user_id,))
    return bool(admin)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    is_admin = await _is_admin(user.id)

    # Admins always get full menu
    if is_admin:
        await message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu_kb(is_admin=True),
            parse_mode="HTML")
        return

    # Check entitlement
    ent = await check_entitlement(user.id)
    if ent["allowed"]:
        await message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu_kb(),
            parse_mode="HTML")
    elif db_user["status"] == "new":
        await message.answer(
            "🤖 <b>TelegramSMM</b>\n\n"
            "Добро пожаловать! Активируйте бесплатный пробный период "
            "или выберите тариф:",
            reply_markup=paywall_kb(show_trial=True),
            parse_mode="HTML")
    else:
        await message.answer(
            "🤖 <b>TelegramSMM</b>\n\n"
            "Ваш доступ истёк. Выберите тариф для продолжения:",
            reply_markup=paywall_kb(show_trial=False),
            parse_mode="HTML")


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_admin = await _is_admin(user_id)

    if is_admin:
        await callback.message.edit_text(
            WELCOME_TEXT,
            reply_markup=main_menu_kb(is_admin=True),
            parse_mode="HTML")
        await callback.answer()
        return

    ent = await check_entitlement(user_id)
    if ent["allowed"]:
        await callback.message.edit_text(
            WELCOME_TEXT,
            reply_markup=main_menu_kb(),
            parse_mode="HTML")
    else:
        db_user = await get_or_create_user(
            user_id, callback.from_user.username, callback.from_user.first_name)
        await callback.message.edit_text(
            "🤖 <b>TelegramSMM</b>\n\n"
            "Ваш доступ истёк. Выберите тариф для продолжения:",
            reply_markup=paywall_kb(show_trial=db_user["status"] == "new"),
            parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "activate_trial")
async def activate_trial(callback: CallbackQuery):
    result = await start_trial(callback.from_user.id)
    if result["ok"]:
        await callback.message.edit_text(
            "🎉 <b>Пробный период активирован!</b>\n\n"
            "У вас есть 24 часа полного доступа.\n"
            "Выберите раздел:",
            reply_markup=main_menu_kb(),
            parse_mode="HTML")
    else:
        await callback.answer(result["error"], show_alert=True)
    await callback.answer()


