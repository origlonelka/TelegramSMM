from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from db.database import execute, fetch_one, fetch_all
from bot.keyboards.inline import settings_menu_kb, stats_kb, stats_sub_kb, MODE_LABELS
from core.scheduler import get_campaign_interval, set_campaign_interval

router = Router()


# --- Настройки ---

async def _show_settings(callback: CallbackQuery):
    interval = await get_campaign_interval()
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu_kb(interval), parse_mode="HTML")


@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery):
    await _show_settings(callback)
    await callback.answer()


@router.callback_query(F.data == "back_settings")
async def back_settings(callback: CallbackQuery):
    await _show_settings(callback)
    await callback.answer()


INTERVAL_OPTIONS = [1, 2, 3, 5, 10, 15, 30, 60]


@router.callback_query(F.data == "settings_interval")
async def settings_interval(callback: CallbackQuery):
    current = await get_campaign_interval()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    row = []
    for m in INTERVAL_OPTIONS:
        label = f"{'✅ ' if m == current else ''}{m} мин"
        row.append(InlineKeyboardButton(text=label, callback_data=f"set_interval_{m}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_settings")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"⏱ <b>Интервал запуска кампаний</b>\n\n"
        f"Текущий: <b>{current} мин</b>\n"
        f"Выберите новый интервал:",
        reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("set_interval_"))
async def set_interval(callback: CallbackQuery):
    minutes = int(callback.data.split("_")[-1])
    await set_campaign_interval(minutes)
    await callback.answer(f"✅ Интервал изменён на {minutes} мин", show_alert=True)
    await _show_settings(callback)


@router.callback_query(F.data == "settings_reset_limits")
async def settings_reset_limits(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]
    await execute(
        "UPDATE accounts SET comments_today = 0, comments_hour = 0 "
        "WHERE owner_user_id = ?", (uid,))
    await callback.answer("✅ Лимиты ваших аккаунтов сброшены", show_alert=True)


# --- Статистика ---

def _user_acc_filter(uid: int) -> tuple[str, tuple]:
    """Returns SQL subquery + params for user's account IDs."""
    return "account_id IN (SELECT id FROM accounts WHERE owner_user_id = ?)", (uid,)


@router.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]
    acc_f, acc_p = _user_acc_filter(uid)

    # Ресурсы
    acc_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM accounts WHERE owner_user_id = ?", (uid,))
    acc_active = await fetch_one(
        "SELECT COUNT(*) as cnt FROM accounts WHERE status = 'active' AND owner_user_id = ?", (uid,))
    acc_limited = await fetch_one(
        "SELECT COUNT(*) as cnt FROM accounts WHERE status = 'limited' AND owner_user_id = ?", (uid,))
    ch_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM channels WHERE owner_user_id = ?", (uid,))
    msg_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM messages WHERE is_active = 1 AND owner_user_id = ?", (uid,))
    camp_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaigns WHERE owner_user_id = ?", (uid,))
    camp_active = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaigns WHERE is_active = 1 AND owner_user_id = ?", (uid,))
    preset_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM presets WHERE owner_user_id = ?", (uid,))
    # Прокси (назначенные на аккаунты пользователя)
    prx_total = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE account_id IN "
        "(SELECT id FROM accounts WHERE owner_user_id = ?)", (uid,))
    prx_alive = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE status = 'alive' AND "
        "account_id IN (SELECT id FROM accounts WHERE owner_user_id = ?)", (uid,))

    # Отправка по периодам (только свои аккаунты)
    hour_sent = await fetch_one(
        f"SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' "
        f"AND sent_at >= datetime('now', '-1 hour') AND {acc_f}", acc_p)
    today_sent = await fetch_one(
        f"SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' "
        f"AND date(sent_at) = date('now') AND {acc_f}", acc_p)
    week_sent = await fetch_one(
        f"SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' "
        f"AND sent_at >= datetime('now', '-7 days') AND {acc_f}", acc_p)
    total_sent = await fetch_one(
        f"SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' AND {acc_f}", acc_p)

    # Ошибки по периодам
    today_errors = await fetch_one(
        f"SELECT COUNT(*) as cnt FROM logs WHERE status = 'error' "
        f"AND date(sent_at) = date('now') AND {acc_f}", acc_p)
    total_errors = await fetch_one(
        f"SELECT COUNT(*) as cnt FROM logs WHERE status = 'error' AND {acc_f}", acc_p)

    # Процент успеха за сегодня
    today_total = today_sent['cnt'] + today_errors['cnt']
    success_rate = (
        f"{today_sent['cnt'] * 100 // today_total}%"
        if today_total > 0 else "—"
    )

    # Разбивка по режимам за сегодня
    mode_stats = await fetch_all(
        f"SELECT mode, COUNT(*) as cnt FROM logs "
        f"WHERE status = 'sent' AND date(sent_at) = date('now') AND {acc_f} "
        f"GROUP BY mode ORDER BY cnt DESC", acc_p)

    # Активная кампания
    active_camp = await fetch_one(
        "SELECT name, mode FROM campaigns WHERE is_active = 1 AND owner_user_id = ? LIMIT 1", (uid,))
    camp_info = "—"
    if active_camp:
        mode_label = MODE_LABELS.get(active_camp['mode'] or 'comments', active_camp['mode'])
        camp_info = f"{active_camp['name']} ({mode_label})"

    text = (
        f"📊 <b>Статистика</b>\n\n"

        f"<b>📦 Ресурсы:</b>\n"
        f"📱 Аккаунты: {acc_active['cnt']} активных"
    )
    if acc_limited['cnt']:
        text += f" / {acc_limited['cnt']} ограничены"
    text += (
        f" / {acc_count['cnt']} всего\n"
        f"📢 Каналов: {ch_count['cnt']}  |  💬 Сообщений: {msg_count['cnt']}\n"
        f"📦 Пресетов: {preset_count['cnt']}\n"
        f"🌐 Прокси: {prx_alive['cnt']} живых / {prx_total['cnt']} всего\n\n"

        f"<b>🚀 Кампания:</b>\n"
        f"Активных: {camp_active['cnt']} / {camp_count['cnt']}\n"
        f"Текущая: {camp_info}\n\n"

        f"<b>📨 Отправка:</b>\n"
        f"За час: {hour_sent['cnt']}\n"
        f"Сегодня: {today_sent['cnt']}  (ошибок: {today_errors['cnt']})\n"
        f"За 7 дней: {week_sent['cnt']}\n"
        f"Всего: {total_sent['cnt']}  (ошибок: {total_errors['cnt']})\n"
        f"Успешность сегодня: {success_rate}\n\n"

        f"<b>🎯 По режимам (сегодня):</b>\n"
    )
    if mode_stats:
        for ms in mode_stats:
            m = ms['mode'] or 'comments'
            label = MODE_LABELS.get(m, m)
            text += f"{label}: {ms['cnt']}\n"
    else:
        text += "Нет данных\n"
    try:
        await callback.message.edit_text(
            text, reply_markup=stats_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Статистика: по аккаунтам ---

@router.callback_query(F.data == "stats_accounts")
async def stats_accounts(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]

    # Топ аккаунтов за сегодня
    top_today = await fetch_all(
        "SELECT a.phone, "
        "SUM(CASE WHEN l.status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN l.status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs l JOIN accounts a ON l.account_id = a.id "
        "WHERE date(l.sent_at) = date('now') AND a.owner_user_id = ? "
        "GROUP BY l.account_id ORDER BY sent DESC LIMIT 10", (uid,))

    # Топ аккаунтов за всё время
    top_all = await fetch_all(
        "SELECT a.phone, COUNT(*) as cnt "
        "FROM logs l JOIN accounts a ON l.account_id = a.id "
        "WHERE l.status = 'sent' AND a.owner_user_id = ? "
        "GROUP BY l.account_id ORDER BY cnt DESC LIMIT 10", (uid,))

    # Статусы аккаунтов
    statuses = await fetch_all(
        "SELECT status, COUNT(*) as cnt FROM accounts "
        "WHERE owner_user_id = ? GROUP BY status", (uid,))

    text = "📱 <b>Статистика по аккаунтам</b>\n\n"

    # Статусы
    text += "<b>Статусы:</b>\n"
    status_icons = {
        "active": "🟢", "limited": "🟡", "inactive": "⚪",
        "registering": "🔄", "importing": "📥", "unauthorized": "🔴",
    }
    for s in statuses:
        icon = status_icons.get(s["status"], "⚪")
        text += f"{icon} {s['status']}: {s['cnt']}\n"

    # Сегодня
    text += "\n<b>Сегодня (топ-10):</b>\n"
    if top_today:
        for i, row in enumerate(top_today, 1):
            err = f" / {row['errors']} ❌" if row['errors'] else ""
            text += f"{i}. <code>{row['phone']}</code> — {row['sent']} ✅{err}\n"
    else:
        text += "Нет данных\n"

    # Всё время
    text += "\n<b>Всё время (топ-10):</b>\n"
    if top_all:
        for i, row in enumerate(top_all, 1):
            text += f"{i}. <code>{row['phone']}</code> — {row['cnt']}\n"
    else:
        text += "Нет данных\n"

    try:
        await callback.message.edit_text(
            text, reply_markup=stats_sub_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Статистика: по каналам ---

@router.callback_query(F.data == "stats_channels")
async def stats_channels(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]

    # Топ каналов за сегодня
    top_today = await fetch_all(
        "SELECT c.username, "
        "SUM(CASE WHEN l.status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN l.status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs l JOIN channels c ON l.channel_id = c.id "
        "WHERE date(l.sent_at) = date('now') AND c.owner_user_id = ? "
        "GROUP BY l.channel_id ORDER BY sent DESC LIMIT 10", (uid,))

    # Топ каналов за всё время
    top_all = await fetch_all(
        "SELECT c.username, COUNT(*) as cnt "
        "FROM logs l JOIN channels c ON l.channel_id = c.id "
        "WHERE l.status = 'sent' AND c.owner_user_id = ? "
        "GROUP BY l.channel_id ORDER BY cnt DESC LIMIT 10", (uid,))

    text = "📢 <b>Статистика по каналам</b>\n\n"

    text += "<b>Сегодня (топ-10):</b>\n"
    if top_today:
        for i, row in enumerate(top_today, 1):
            err = f" / {row['errors']} ❌" if row['errors'] else ""
            text += f"{i}. @{row['username']} — {row['sent']} ✅{err}\n"
    else:
        text += "Нет данных\n"

    text += "\n<b>Всё время (топ-10):</b>\n"
    if top_all:
        for i, row in enumerate(top_all, 1):
            text += f"{i}. @{row['username']} — {row['cnt']}\n"
    else:
        text += "Нет данных\n"

    try:
        await callback.message.edit_text(
            text, reply_markup=stats_sub_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Статистика: ошибки ---

@router.callback_query(F.data == "stats_errors")
async def stats_errors(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]
    acc_f, acc_p = _user_acc_filter(uid)

    # Последние 15 ошибок
    recent = await fetch_all(
        f"SELECT l.error, l.sent_at, a.phone, c.username "
        f"FROM logs l "
        f"LEFT JOIN accounts a ON l.account_id = a.id "
        f"LEFT JOIN channels c ON l.channel_id = c.id "
        f"WHERE l.status = 'error' AND a.owner_user_id = ? "
        f"ORDER BY l.sent_at DESC LIMIT 15", (uid,))

    # Группировка ошибок за сегодня
    error_groups = await fetch_all(
        f"SELECT "
        f"CASE "
        f"  WHEN error LIKE '%FloodWait%' THEN 'FloodWait' "
        f"  WHEN error LIKE '%PeerFlood%' THEN 'PeerFlood' "
        f"  WHEN error LIKE '%UserBannedInChannel%' THEN 'UserBannedInChannel' "
        f"  WHEN error LIKE '%DELETED%' THEN 'Мёртвый аккаунт' "
        f"  WHEN error LIKE '%ChatWriteForbidden%' THEN 'Нет доступа к чату' "
        f"  WHEN error LIKE '%SlowmodeWait%' THEN 'SlowmodeWait' "
        f"  WHEN error LIKE '%timeout%' OR error LIKE '%Timeout%' THEN 'Таймаут' "
        f"  ELSE 'Другое' "
        f"END as error_type, "
        f"COUNT(*) as cnt "
        f"FROM logs WHERE status = 'error' AND date(sent_at) = date('now') AND {acc_f} "
        f"GROUP BY error_type ORDER BY cnt DESC", acc_p)

    text = "❌ <b>Ошибки</b>\n\n"

    # Группы ошибок за сегодня
    text += "<b>Сегодня по типам:</b>\n"
    if error_groups:
        for eg in error_groups:
            text += f"• {eg['error_type']}: {eg['cnt']}\n"
    else:
        text += "Нет ошибок за сегодня\n"

    # Последние ошибки
    text += "\n<b>Последние ошибки:</b>\n"
    if recent:
        for r in recent:
            phone = r['phone'] or '?'
            channel = f"@{r['username']}" if r['username'] else '?'
            error = (r['error'] or '')[:60]
            time = r['sent_at'][11:16] if r['sent_at'] and len(r['sent_at']) > 16 else '?'
            text += f"<code>{time}</code> {phone} → {channel}\n   ↳ {error}\n"
    else:
        text += "Нет данных\n"

    try:
        await callback.message.edit_text(
            text, reply_markup=stats_sub_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Статистика: по дням ---

@router.callback_query(F.data == "stats_daily")
async def stats_daily(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]
    acc_f, acc_p = _user_acc_filter(uid)

    # Статистика за последние 7 дней
    daily = await fetch_all(
        f"SELECT date(sent_at) as day, "
        f"SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        f"SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        f"FROM logs "
        f"WHERE sent_at >= datetime('now', '-7 days') AND {acc_f} "
        f"GROUP BY day ORDER BY day DESC", acc_p)

    text = "📅 <b>Статистика по дням</b>\n\n"

    if daily:
        text += "<code>Дата        | ✅ Отпр | ❌ Ошиб</code>\n"
        text += "<code>────────────┼────────┼───────</code>\n"
        for d in daily:
            day = d['day'] or '?'
            sent = str(d['sent']).rjust(6)
            errors = str(d['errors']).rjust(5)
            text += f"<code>{day}  | {sent} | {errors}</code>\n"

        # Итого
        total_s = sum(d['sent'] for d in daily)
        total_e = sum(d['errors'] for d in daily)
        text += f"<code>────────────┼────────┼───────</code>\n"
        text += f"<code>Итого       | {str(total_s).rjust(6)} | {str(total_e).rjust(5)}</code>\n"

        # Среднее в день
        avg = total_s / len(daily) if daily else 0
        text += f"\n📈 Среднее в день: {avg:.0f}"
    else:
        text += "Нет данных за последние 7 дней"

    try:
        await callback.message.edit_text(
            text, reply_markup=stats_sub_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


# --- Статистика: по режимам ---

@router.callback_query(F.data == "stats_modes")
async def stats_modes(callback: CallbackQuery, db_user: dict):
    uid = db_user["telegram_id"]
    acc_f, acc_p = _user_acc_filter(uid)

    # Разбивка по режимам за сегодня
    today_modes = await fetch_all(
        f"SELECT mode, "
        f"SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        f"SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        f"FROM logs WHERE date(sent_at) = date('now') AND {acc_f} "
        f"GROUP BY mode ORDER BY sent DESC", acc_p)

    # Разбивка по режимам за 7 дней
    week_modes = await fetch_all(
        f"SELECT mode, "
        f"SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        f"SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        f"FROM logs WHERE sent_at >= datetime('now', '-7 days') AND {acc_f} "
        f"GROUP BY mode ORDER BY sent DESC", acc_p)

    # Разбивка по режимам за всё время
    all_modes = await fetch_all(
        f"SELECT mode, "
        f"SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        f"SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        f"FROM logs WHERE {acc_f} GROUP BY mode ORDER BY sent DESC", acc_p)

    text = "🎯 <b>Статистика по режимам</b>\n\n"

    # Сегодня
    text += "<b>Сегодня:</b>\n"
    if today_modes:
        for ms in today_modes:
            m = ms['mode'] or 'comments'
            label = MODE_LABELS.get(m, m)
            err = f" / {ms['errors']} ❌" if ms['errors'] else ""
            text += f"{label}: {ms['sent']} ✅{err}\n"
    else:
        text += "Нет данных\n"

    # За 7 дней
    text += "\n<b>За 7 дней:</b>\n"
    if week_modes:
        for ms in week_modes:
            m = ms['mode'] or 'comments'
            label = MODE_LABELS.get(m, m)
            err = f" / {ms['errors']} ❌" if ms['errors'] else ""
            text += f"{label}: {ms['sent']} ✅{err}\n"
    else:
        text += "Нет данных\n"

    # Всё время
    text += "\n<b>Всё время:</b>\n"
    if all_modes:
        for ms in all_modes:
            m = ms['mode'] or 'comments'
            label = MODE_LABELS.get(m, m)
            err = f" / {ms['errors']} ❌" if ms['errors'] else ""
            text += f"{label}: {ms['sent']} ✅{err}\n"

        # Итоги
        total_s = sum(ms['sent'] for ms in all_modes)
        total_e = sum(ms['errors'] for ms in all_modes)
        text += f"\n📊 Итого: {total_s} ✅ / {total_e} ❌"
    else:
        text += "Нет данных\n"

    try:
        await callback.message.edit_text(
            text, reply_markup=stats_sub_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()
