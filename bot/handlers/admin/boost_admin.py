"""Admin panel for boost (nakrutka) settings."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db.database import execute, fetch_one, fetch_all
from services import likedrom
from services.boost_manager import sync_services

router = Router()


class BoostSettings(StatesGroup):
    markup = State()
    api_key = State()


# ─── Главная страница накрутки в админке ─────────────────

@router.callback_query(F.data == "admin_boost")
async def admin_boost_menu(callback: CallbackQuery):
    # Текущая наценка
    markup_row = await fetch_one(
        "SELECT value FROM bot_settings WHERE key = 'boost_markup_percent'")
    markup = markup_row["value"] if markup_row else "40"

    # Кол-во сервисов
    svc_row = await fetch_one(
        "SELECT COUNT(*) as cnt FROM boost_services WHERE is_active = 1")
    svc_count = svc_row["cnt"] if svc_row else 0

    # Кол-во заказов
    orders_row = await fetch_one(
        "SELECT COUNT(*) as total, "
        "COALESCE(SUM(CASE WHEN status IN ('pending','processing','in_progress') "
        "THEN 1 ELSE 0 END), 0) as active, "
        "COALESCE(SUM(price_rub), 0) as revenue, "
        "COALESCE(SUM(cost_rub), 0) as costs "
        "FROM boost_orders")

    # Баланс LikeDrom
    try:
        ld_balance = await likedrom.get_balance()
        ld_text = f"{ld_balance:.2f} ₽"
    except Exception:
        ld_text = "Ошибка"

    text = (
        f"🚀 <b>Управление накруткой</b>\n\n"
        f"📊 <b>Наценка:</b> {markup}%\n"
        f"🔧 <b>Сервисов:</b> {svc_count}\n"
        f"💰 <b>Баланс LikeDrom:</b> {ld_text}\n\n"
        f"📋 <b>Заказы:</b>\n"
        f"  Всего: {orders_row['total']}\n"
        f"  Активных: {orders_row['active']}\n"
        f"  Выручка: {orders_row['revenue']:.2f} ₽\n"
        f"  Себестоимость: {orders_row['costs']:.2f} ₽\n"
        f"  Прибыль: {orders_row['revenue'] - orders_row['costs']:.2f} ₽"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"📊 Наценка ({markup}%)", callback_data="admin_boost_markup"),
         InlineKeyboardButton(
            text="🔑 API ключ", callback_data="admin_boost_apikey")],
        [InlineKeyboardButton(
            text="🔄 Синхронизировать сервисы", callback_data="admin_boost_sync")],
        [InlineKeyboardButton(
            text="📋 Последние заказы", callback_data="admin_boost_orders")],
        [InlineKeyboardButton(
            text="◀️ Назад", callback_data="admin_panel")],
    ]
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


# ─── Изменить наценку ────────────────────────────────────

@router.callback_query(F.data == "admin_boost_markup")
async def admin_boost_markup(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BoostSettings.markup)
    await callback.message.edit_text(
        "📊 <b>Наценка</b>\n\n"
        "Введите новый процент наценки (например, 40):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_boost")]]),
        parse_mode="HTML")
    await callback.answer()


@router.message(BoostSettings.markup)
async def admin_boost_markup_set(message: Message, state: FSMContext):
    try:
        val = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите число:")
        return

    if val < 0 or val > 500:
        await message.answer("❌ Допустимый диапазон: 0–500%")
        return

    await state.clear()
    existing = await fetch_one(
        "SELECT 1 FROM bot_settings WHERE key = 'boost_markup_percent'")
    if existing:
        await execute(
            "UPDATE bot_settings SET value = ? WHERE key = 'boost_markup_percent'",
            (str(val),))
    else:
        await execute(
            "INSERT INTO bot_settings (key, value) VALUES ('boost_markup_percent', ?)",
            (str(val),))

    # Пересинхронизировать цены
    count = await sync_services()
    await message.answer(
        f"✅ Наценка установлена: {val}%\n"
        f"Обновлено {count} сервисов с новыми ценами.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_boost")]]))


# ─── Изменить API ключ ───────────────────────────────────

@router.callback_query(F.data == "admin_boost_apikey")
async def admin_boost_apikey(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BoostSettings.api_key)
    await callback.message.edit_text(
        "🔑 <b>API ключ LikeDrom</b>\n\n"
        "Введите новый API ключ:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_boost")]]),
        parse_mode="HTML")
    await callback.answer()


@router.message(BoostSettings.api_key)
async def admin_boost_apikey_set(message: Message, state: FSMContext):
    key = message.text.strip()
    if len(key) < 10:
        await message.answer("❌ Ключ слишком короткий")
        return

    await state.clear()
    existing = await fetch_one(
        "SELECT 1 FROM bot_settings WHERE key = 'likedrom_api_key'")
    if existing:
        await execute(
            "UPDATE bot_settings SET value = ? WHERE key = 'likedrom_api_key'",
            (key,))
    else:
        await execute(
            "INSERT INTO bot_settings (key, value) VALUES ('likedrom_api_key', ?)",
            (key,))

    await message.answer(
        f"✅ API ключ обновлён: {key[:8]}...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_boost")]]))


# ─── Синхронизация сервисов ──────────────────────────────

@router.callback_query(F.data == "admin_boost_sync")
async def admin_boost_sync(callback: CallbackQuery):
    await callback.answer("Синхронизация...", show_alert=False)
    try:
        count = await sync_services()
        await callback.message.edit_text(
            f"✅ Синхронизировано {count} сервисов!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_boost")]]),
            parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка синхронизации: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_boost")]]),
            parse_mode="HTML")


# ─── Последние заказы ────────────────────────────────────

@router.callback_query(F.data == "admin_boost_orders")
async def admin_boost_orders(callback: CallbackQuery):
    rows = await fetch_all(
        "SELECT bo.*, u.username FROM boost_orders bo "
        "LEFT JOIN users u ON bo.user_telegram_id = u.telegram_id "
        "ORDER BY bo.id DESC LIMIT 15")

    if not rows:
        await callback.message.edit_text(
            "📋 Заказов пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_boost")]]),
            parse_mode="HTML")
        await callback.answer()
        return

    status_emoji = {
        "pending": "⏳", "processing": "🔄", "in_progress": "🔄",
        "completed": "✅", "partial": "⚠️", "canceled": "❌", "error": "❌",
    }

    lines = ["📋 <b>Последние заказы накрутки</b>\n"]
    for o in rows:
        emoji = status_emoji.get(o["status"], "❓")
        user = f"@{o['username']}" if o["username"] else f"#{o['user_telegram_id']}"
        name = (o["service_name"] or "")[:20]
        lines.append(
            f"{emoji} #{o['id']} | {user} | {name} | "
            f"{o['quantity']} | {o['price_rub']:.2f}₽ / {o['cost_rub']:.2f}₽")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_boost_orders")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_boost")]]),
        parse_mode="HTML")
    await callback.answer()
