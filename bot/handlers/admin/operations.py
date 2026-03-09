"""Admin dashboards: users, finance, operations, YooKassa settings."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import fetch_one, fetch_all
from core.scheduler import get_campaign_interval, set_campaign_interval

router = Router()

INTERVAL_OPTIONS = [1, 2, 3, 5, 10, 15, 30, 60]


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
        [InlineKeyboardButton(text="💵 YooKassa", callback_data="adm_yookassa"),
         InlineKeyboardButton(text="🚀 Накрутка", callback_data="admin_boost")],
        [InlineKeyboardButton(text="⏱ Интервал кампаний", callback_data="adm_interval")],
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


# --- YooKassa settings (superadmin only) ---

@router.callback_query(F.data == "adm_yookassa")
async def yookassa_settings(callback: CallbackQuery, admin: dict):
    if admin["role"] != "superadmin":
        await callback.answer("Только для суперадминов", show_alert=True)
        return

    from core.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, WEBHOOK_PORT, WEBHOOK_SECRET, BOT_URL

    shop_status = "✅ Установлен" if YOOKASSA_SHOP_ID else "❌ Не установлен"
    key_status = "✅ Установлен" if YOOKASSA_SECRET_KEY else "❌ Не установлен"
    key_preview = YOOKASSA_SECRET_KEY[:8] + "..." if YOOKASSA_SECRET_KEY else "—"

    text = (
        "💵 <b>Настройки YooKassa</b>\n\n"
        f"Shop ID: {shop_status}\n"
        f"  <code>{YOOKASSA_SHOP_ID or '—'}</code>\n\n"
        f"Secret Key: {key_status}\n"
        f"  <code>{key_preview}</code>\n\n"
        f"Webhook порт: <code>{WEBHOOK_PORT}</code>\n"
        f"Webhook secret: <code>{'***' if WEBHOOK_SECRET else '—'}</code>\n"
        f"Bot URL: <code>{BOT_URL or '—'}</code>\n\n"
        "Для изменения отредактируйте файл <code>.env</code> "
        "и перезапустите бота."
    )
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
        ]), parse_mode="HTML")
    await callback.answer()


# --- Интервал кампаний ---

@router.callback_query(F.data == "adm_interval")
async def adm_interval(callback: CallbackQuery):
    current = await get_campaign_interval()
    buttons = []
    row = []
    for m in INTERVAL_OPTIONS:
        label = f"{'✅ ' if m == current else ''}{m} мин"
        row.append(InlineKeyboardButton(text=label, callback_data=f"adm_set_iv_{m}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"⏱ <b>Интервал запуска кампаний</b>\n\n"
        f"Текущий: <b>{current} мин</b>\n"
        f"Как часто бот проверяет и запускает активные кампании.\n\n"
        f"Выберите новый интервал:",
        reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_set_iv_"))
async def adm_set_interval(callback: CallbackQuery):
    minutes = int(callback.data.split("_")[-1])
    await set_campaign_interval(minutes)
    await callback.answer(f"✅ Интервал изменён на {minutes} мин", show_alert=True)
    current = await get_campaign_interval()
    buttons = []
    row = []
    for m in INTERVAL_OPTIONS:
        label = f"{'✅ ' if m == current else ''}{m} мин"
        row.append(InlineKeyboardButton(text=label, callback_data=f"adm_set_iv_{m}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"⏱ <b>Интервал запуска кампаний</b>\n\n"
        f"Текущий: <b>{current} мин</b>\n"
        f"Как часто бот проверяет и запускает активные кампании.\n\n"
        f"Выберите новый интервал:",
        reply_markup=kb, parse_mode="HTML")
