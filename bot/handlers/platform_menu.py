"""Platform selection menu: Telegram / Instagram / Накрутка."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards.inline import (
    platform_menu_kb, telegram_menu_kb, back_kb,
)

router = Router()


@router.callback_query(F.data == "platform_telegram")
async def platform_telegram(callback: CallbackQuery, state: FSMContext):
    """Telegram — текущее SMM-меню с аккаунтом и подпиской."""
    await state.clear()
    await callback.message.edit_text(
        "📱 <b>Telegram SMM</b>\n\n"
        "Управление аккаунтами, каналами, кампаниями и шаблонами.",
        reply_markup=telegram_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "platform_instagram")
async def platform_instagram(callback: CallbackQuery):
    """Instagram — заглушка."""
    await callback.message.edit_text(
        "📷 <b>Instagram</b>\n\n"
        "🔧 Раздел в разработке.\n"
        "Следите за обновлениями!",
        reply_markup=back_kb("platform"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "back_platform")
async def back_platform(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору платформы."""
    await state.clear()
    from bot.handlers.start import _is_admin
    is_admin = await _is_admin(callback.from_user.id)
    await callback.message.edit_text(
        "🤖 <b>TelegramSMM</b>\n\nВыберите раздел:",
        reply_markup=platform_menu_kb(is_admin=is_admin),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "back_telegram")
async def back_telegram(callback: CallbackQuery, state: FSMContext):
    """Возврат к меню Telegram."""
    await state.clear()
    await callback.message.edit_text(
        "📱 <b>Telegram SMM</b>\n\n"
        "Управление аккаунтами, каналами, кампаниями и шаблонами.",
        reply_markup=telegram_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
