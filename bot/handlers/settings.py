from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from db.database import execute, fetch_one, fetch_all
from bot.keyboards.inline import settings_menu_kb, stats_kb, stats_sub_kb, back_kb, MODE_LABELS

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
    # Ресурсы
    acc_count = await fetch_one("SELECT COUNT(*) as cnt FROM accounts")
    acc_active = await fetch_one(
        "SELECT COUNT(*) as cnt FROM accounts WHERE status = 'active'")
    acc_limited = await fetch_one(
        "SELECT COUNT(*) as cnt FROM accounts WHERE status = 'limited'")
    ch_count = await fetch_one("SELECT COUNT(*) as cnt FROM channels")
    msg_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM messages WHERE is_active = 1")
    camp_count = await fetch_one("SELECT COUNT(*) as cnt FROM campaigns")
    camp_active = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaigns WHERE is_active = 1")
    preset_count = await fetch_one("SELECT COUNT(*) as cnt FROM presets")
    tpl_count = await fetch_one("SELECT COUNT(*) as cnt FROM account_templates")

    # Прокси
    prx_total = await fetch_one("SELECT COUNT(*) as cnt FROM proxies")
    prx_alive = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE status = 'alive'")
    prx_assigned = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE account_id IS NOT NULL")

    # Отправка по периодам
    hour_sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' "
        "AND sent_at >= datetime('now', '-1 hour')")
    today_sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' "
        "AND date(sent_at) = date('now')")
    week_sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent' "
        "AND sent_at >= datetime('now', '-7 days')")
    total_sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'sent'")

    # Ошибки по периодам
    today_errors = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'error' "
        "AND date(sent_at) = date('now')")
    total_errors = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE status = 'error'")

    # Процент успеха за сегодня
    today_total = today_sent['cnt'] + today_errors['cnt']
    success_rate = (
        f"{today_sent['cnt'] * 100 // today_total}%"
        if today_total > 0 else "—"
    )

    # Разбивка по режимам за сегодня
    mode_stats = await fetch_all(
        "SELECT mode, COUNT(*) as cnt FROM logs "
        "WHERE status = 'sent' AND date(sent_at) = date('now') "
        "GROUP BY mode ORDER BY cnt DESC")

    # Активная кампания
    active_camp = await fetch_one(
        "SELECT name, mode FROM campaigns WHERE is_active = 1 LIMIT 1")
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
        f"📦 Пресетов: {preset_count['cnt']}  |  👤 Шаблонов: {tpl_count['cnt']}\n"
        f"🌐 Прокси: {prx_alive['cnt']} живых / {prx_assigned['cnt']} назначено / {prx_total['cnt']} всего\n\n"

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
async def stats_accounts(callback: CallbackQuery):
    # Топ аккаунтов за сегодня
    top_today = await fetch_all(
        "SELECT a.phone, "
        "SUM(CASE WHEN l.status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN l.status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs l JOIN accounts a ON l.account_id = a.id "
        "WHERE date(l.sent_at) = date('now') "
        "GROUP BY l.account_id ORDER BY sent DESC LIMIT 10")

    # Топ аккаунтов за всё время
    top_all = await fetch_all(
        "SELECT a.phone, COUNT(*) as cnt "
        "FROM logs l JOIN accounts a ON l.account_id = a.id "
        "WHERE l.status = 'sent' "
        "GROUP BY l.account_id ORDER BY cnt DESC LIMIT 10")

    # Статусы аккаунтов
    statuses = await fetch_all(
        "SELECT status, COUNT(*) as cnt FROM accounts GROUP BY status")

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
async def stats_channels(callback: CallbackQuery):
    # Топ каналов за сегодня
    top_today = await fetch_all(
        "SELECT c.username, "
        "SUM(CASE WHEN l.status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN l.status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs l JOIN channels c ON l.channel_id = c.id "
        "WHERE date(l.sent_at) = date('now') "
        "GROUP BY l.channel_id ORDER BY sent DESC LIMIT 10")

    # Топ каналов за всё время
    top_all = await fetch_all(
        "SELECT c.username, COUNT(*) as cnt "
        "FROM logs l JOIN channels c ON l.channel_id = c.id "
        "WHERE l.status = 'sent' "
        "GROUP BY l.channel_id ORDER BY cnt DESC LIMIT 10")

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
async def stats_errors(callback: CallbackQuery):
    # Последние 15 ошибок
    recent = await fetch_all(
        "SELECT l.error, l.sent_at, a.phone, c.username "
        "FROM logs l "
        "LEFT JOIN accounts a ON l.account_id = a.id "
        "LEFT JOIN channels c ON l.channel_id = c.id "
        "WHERE l.status = 'error' "
        "ORDER BY l.sent_at DESC LIMIT 15")

    # Группировка ошибок за сегодня
    error_groups = await fetch_all(
        "SELECT "
        "CASE "
        "  WHEN error LIKE '%FloodWait%' THEN 'FloodWait' "
        "  WHEN error LIKE '%PeerFlood%' THEN 'PeerFlood' "
        "  WHEN error LIKE '%UserBannedInChannel%' THEN 'UserBannedInChannel' "
        "  WHEN error LIKE '%DELETED%' THEN 'Мёртвый аккаунт' "
        "  WHEN error LIKE '%ChatWriteForbidden%' THEN 'Нет доступа к чату' "
        "  WHEN error LIKE '%SlowmodeWait%' THEN 'SlowmodeWait' "
        "  WHEN error LIKE '%timeout%' OR error LIKE '%Timeout%' THEN 'Таймаут' "
        "  ELSE 'Другое' "
        "END as error_type, "
        "COUNT(*) as cnt "
        "FROM logs WHERE status = 'error' AND date(sent_at) = date('now') "
        "GROUP BY error_type ORDER BY cnt DESC")

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
async def stats_daily(callback: CallbackQuery):
    # Статистика за последние 7 дней
    daily = await fetch_all(
        "SELECT date(sent_at) as day, "
        "SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs "
        "WHERE sent_at >= datetime('now', '-7 days') "
        "GROUP BY day ORDER BY day DESC")

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
async def stats_modes(callback: CallbackQuery):
    # Разбивка по режимам за сегодня
    today_modes = await fetch_all(
        "SELECT mode, "
        "SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs WHERE date(sent_at) = date('now') "
        "GROUP BY mode ORDER BY sent DESC")

    # Разбивка по режимам за 7 дней
    week_modes = await fetch_all(
        "SELECT mode, "
        "SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs WHERE sent_at >= datetime('now', '-7 days') "
        "GROUP BY mode ORDER BY sent DESC")

    # Разбивка по режимам за всё время
    all_modes = await fetch_all(
        "SELECT mode, "
        "SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent, "
        "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
        "FROM logs GROUP BY mode ORDER BY sent DESC")

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
