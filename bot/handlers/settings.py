from aiogram import Router, F
from aiogram.types import CallbackQuery
from db.database import execute, fetch_one, fetch_all
from bot.keyboards.inline import settings_menu_kb, stats_kb, back_kb

router = Router()


# --- Настройки ---

@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery):
    from core.config import API_ID, API_HASH
    api_status = "✅ Установлены" if API_ID and API_HASH else "❌ Не установлены"
    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"API данные: {api_status}\n"
        f"API ID: <code>{API_ID or '—'}</code>\n"
        f"API Hash: <code>{API_HASH[:8] + '...' if API_HASH else '—'}</code>"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "settings_api")
async def settings_api(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔑 <b>API настройки</b>\n\n"
        "API ID и API Hash задаются в файле <code>.env</code>.\n\n"
        "1. Перейдите на my.telegram.org\n"
        "2. Создайте приложение\n"
        "3. Скопируйте API ID и API Hash в .env файл",
        reply_markup=back_kb("settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "back_settings")
async def back_settings(callback: CallbackQuery):
    from core.config import API_ID, API_HASH
    api_status = "✅ Установлены" if API_ID and API_HASH else "❌ Не установлены"
    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"API данные: {api_status}\n"
        f"API ID: <code>{API_ID or '—'}</code>\n"
        f"API Hash: <code>{API_HASH[:8] + '...' if API_HASH else '—'}</code>"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "settings_reset_limits")
async def settings_reset_limits(callback: CallbackQuery):
    await execute("UPDATE accounts SET comments_today = 0, comments_hour = 0")
    await callback.answer("✅ Лимиты всех аккаунтов сброшены", show_alert=True)


# --- Статистика ---

@router.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    acc_count = await fetch_one("SELECT COUNT(*) as cnt FROM accounts")
    acc_active = await fetch_one("SELECT COUNT(*) as cnt FROM accounts WHERE status = 'active'")
    ch_count = await fetch_one("SELECT COUNT(*) as cnt FROM channels")
    msg_count = await fetch_one("SELECT COUNT(*) as cnt FROM messages WHERE is_active = 1")
    camp_count = await fetch_one("SELECT COUNT(*) as cnt FROM campaigns")
    camp_active = await fetch_one("SELECT COUNT(*) as cnt FROM campaigns WHERE is_active = 1")

    total_sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent'")
    total_errors = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'error'")
    today_sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' AND date(sent_at) = date('now')")

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📱 Аккаунтов: {acc_count['cnt']} (активных: {acc_active['cnt']})\n"
        f"📢 Каналов: {ch_count['cnt']}\n"
        f"💬 Сообщений: {msg_count['cnt']}\n"
        f"🚀 Кампаний: {camp_count['cnt']} (активных: {camp_active['cnt']})\n\n"
        f"📨 <b>Отправка:</b>\n"
        f"Сегодня: {today_sent['cnt']}\n"
        f"Всего отправлено: {total_sent['cnt']}\n"
        f"Ошибок: {total_errors['cnt']}"
    )
    await callback.message.edit_text(text, reply_markup=stats_kb(), parse_mode="HTML")
    await callback.answer()
