"""Admin dashboards: users, finance, operations."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.database import fetch_one, fetch_all

router = Router()


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_dash_users"),
         InlineKeyboardButton(text="💰 Финансы", callback_data="adm_dash_finance")],
        [InlineKeyboardButton(text="📊 Операции", callback_data="adm_dash_ops")],
        [InlineKeyboardButton(text="👤 Управление", callback_data="adm_users"),
         InlineKeyboardButton(text="🛡 Роли", callback_data="adm_roles")],
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="adm_plans"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promos")],
        [InlineKeyboardButton(text="🎫 Тикеты", callback_data="adm_tickets"),
         InlineKeyboardButton(text="📋 Аудит", callback_data="adm_audit")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>\n\nВыберите раздел:",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_back")
async def adm_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>\n\nВыберите раздел:",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_dash_users")
async def dash_users(callback: CallbackQuery):
    new = await fetch_one("SELECT COUNT(*) as c FROM users WHERE status = 'new'")
    trial = await fetch_one("SELECT COUNT(*) as c FROM users WHERE status = 'trial_active'")
    paid = await fetch_one("SELECT COUNT(*) as c FROM users WHERE status = 'subscription_active'")
    expired = await fetch_one("SELECT COUNT(*) as c FROM users WHERE status = 'expired'")
    blocked = await fetch_one("SELECT COUNT(*) as c FROM users WHERE status = 'blocked'")
    total = await fetch_one("SELECT COUNT(*) as c FROM users")

    text = (
        "👥 <b>Дашборд пользователей</b>\n\n"
        f"Всего: {total['c']}\n"
        f"🆕 Новые: {new['c']}\n"
        f"⏳ Триал: {trial['c']}\n"
        f"💳 Платные: {paid['c']}\n"
        f"⌛ Истёкшие: {expired['c']}\n"
        f"🚫 Заблокированные: {blocked['c']}"
    )
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
        ]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_dash_finance")
async def dash_finance(callback: CallbackQuery):
    today = await fetch_one(
        "SELECT COALESCE(SUM(amount_rub), 0) as s FROM subscriptions "
        "WHERE status = 'succeeded' AND date(started_at) = date('now')")
    week = await fetch_one(
        "SELECT COALESCE(SUM(amount_rub), 0) as s FROM subscriptions "
        "WHERE status = 'succeeded' AND started_at >= datetime('now', '-7 days')")
    month = await fetch_one(
        "SELECT COALESCE(SUM(amount_rub), 0) as s FROM subscriptions "
        "WHERE status = 'succeeded' AND started_at >= datetime('now', '-30 days')")
    total = await fetch_one(
        "SELECT COALESCE(SUM(amount_rub), 0) as s FROM subscriptions "
        "WHERE status = 'succeeded'")
    active_subs = await fetch_one(
        "SELECT COUNT(*) as c FROM subscriptions "
        "WHERE status = 'succeeded' AND expires_at > datetime('now')")

    text = (
        "💰 <b>Дашборд финансов</b>\n\n"
        f"Сегодня: {today['s']} ₽\n"
        f"За 7 дней: {week['s']} ₽\n"
        f"За 30 дней: {month['s']} ₽\n"
        f"Всего: {total['s']} ₽\n\n"
        f"Активных подписок: {active_subs['c']}"
    )
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
        ]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_dash_ops")
async def dash_ops(callback: CallbackQuery):
    errors_24h = await fetch_one(
        "SELECT COUNT(*) as c FROM logs WHERE status = 'error' "
        "AND sent_at >= datetime('now', '-24 hours')")
    sent_24h = await fetch_one(
        "SELECT COUNT(*) as c FROM logs WHERE status = 'sent' "
        "AND sent_at >= datetime('now', '-24 hours')")
    flood_24h = await fetch_one(
        "SELECT COUNT(*) as c FROM logs WHERE error LIKE '%FloodWait%' "
        "AND sent_at >= datetime('now', '-24 hours')")
    active_camps = await fetch_one(
        "SELECT COUNT(*) as c FROM campaigns WHERE is_active = 1")
    active_accs = await fetch_one(
        "SELECT COUNT(*) as c FROM accounts WHERE status = 'active'")

    total = (sent_24h['c'] + errors_24h['c']) or 1
    success_rate = round(sent_24h['c'] / total * 100, 1)

    text = (
        "📊 <b>Дашборд операций</b> (24ч)\n\n"
        f"✅ Отправлено: {sent_24h['c']}\n"
        f"❌ Ошибки: {errors_24h['c']}\n"
        f"🌊 FloodWait: {flood_24h['c']}\n"
        f"📈 Успешность: {success_rate}%\n\n"
        f"🚀 Активных кампаний: {active_camps['c']}\n"
        f"📱 Активных аккаунтов: {active_accs['c']}"
    )
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
        ]), parse_mode="HTML")
    await callback.answer()
