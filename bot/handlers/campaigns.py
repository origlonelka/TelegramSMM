from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    campaigns_menu_kb, campaign_list_kb, campaign_item_kb,
    camp_confirm_del_kb, camp_select_items_kb, camp_limits_kb, back_kb,
    camp_mode_kb, camp_logs_kb, MODE_LABELS,
)

router = Router()


class AddCampaign(StatesGroup):
    name = State()


class SetLimit(StatesGroup):
    value = State()


# --- Меню кампаний ---

@router.callback_query(F.data.in_({"campaigns", "back_campaigns"}))
async def campaigns_menu(callback: CallbackQuery, state: FSMContext, db_user: dict):
    await state.clear()
    count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaigns WHERE owner_user_id = ?",
        (db_user["telegram_id"],))
    text = f"🚀 <b>Кампании</b>\n\nВсего: {count['cnt']}"
    await callback.message.edit_text(text, reply_markup=campaigns_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "camp_list")
async def camp_list(callback: CallbackQuery, db_user: dict):
    campaigns = await fetch_all(
        "SELECT id, name, is_active FROM campaigns WHERE owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    if not campaigns:
        await callback.answer("Список пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Список кампаний:</b>",
        reply_markup=campaign_list_kb(campaigns),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр ---

@router.callback_query(F.data.startswith("camp_view_"))
async def camp_view(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one(
        "SELECT * FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    ch_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    acc_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    msg_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaign_messages WHERE campaign_id = ?", (camp_id,))

    status = "🟢 Активна" if camp["is_active"] else "🔴 Остановлена"
    mode = camp["mode"] or "comments"
    mode_label = ", ".join(MODE_LABELS.get(m, m) for m in mode.split(","))
    text = (
        f"🚀 <b>Кампания: {camp['name']}</b>\n\n"
        f"Статус: {status}\n"
        f"Режим: {mode_label}\n"
        f"Каналов: {ch_count['cnt']}\n"
        f"Аккаунтов: {acc_count['cnt']}\n"
        f"Сообщений: {msg_count['cnt']}\n\n"
        f"⚙️ <b>Лимиты:</b>\n"
        f"Задержка: {camp['delay_min']}–{camp['delay_max']} сек\n"
        f"В час: {camp['hourly_limit']}\n"
        f"В день: {camp['daily_limit']}"
    )
    await callback.message.edit_text(
        text, reply_markup=campaign_item_kb(camp_id, bool(camp["is_active"])),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Создание ---

@router.callback_query(F.data == "camp_add")
async def camp_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCampaign.name)
    await callback.message.edit_text(
        "🚀 Введите название кампании:",
        reply_markup=back_kb("campaigns"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddCampaign.name)
async def camp_add_name(message: Message, state: FSMContext, db_user: dict):
    name = message.text.strip()
    await state.clear()
    camp_id = await execute_returning(
        "INSERT INTO campaigns (name, owner_user_id) VALUES (?, ?)",
        (name, db_user["telegram_id"]),
    )
    await message.answer(
        f"✅ Кампания «{name}» создана (#{camp_id}).\n"
        f"Теперь добавьте каналы, аккаунты и сообщения.",
        reply_markup=campaign_item_kb(camp_id, False),
    )


# --- Вкл/Выкл ---

@router.callback_query(F.data.startswith("camp_toggle_"))
async def camp_toggle(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one(
        "SELECT is_active FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return
    new_status = 0 if camp["is_active"] else 1
    await execute("UPDATE campaigns SET is_active = ? WHERE id = ?", (new_status, camp_id))
    await callback.answer("✅ Статус изменён")

    # Перерисовать карточку
    camp = await fetch_one("SELECT * FROM campaigns WHERE id = ?", (camp_id,))
    ch_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    acc_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    msg_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM campaign_messages WHERE campaign_id = ?", (camp_id,))
    status = "🟢 Активна" if camp["is_active"] else "🔴 Остановлена"
    mode = camp["mode"] or "comments"
    mode_label = ", ".join(MODE_LABELS.get(m, m) for m in mode.split(","))
    text = (
        f"🚀 <b>Кампания: {camp['name']}</b>\n\n"
        f"Статус: {status}\n"
        f"Режим: {mode_label}\n"
        f"Каналов: {ch_count['cnt']}\n"
        f"Аккаунтов: {acc_count['cnt']}\n"
        f"Сообщений: {msg_count['cnt']}\n\n"
        f"⚙️ <b>Лимиты:</b>\n"
        f"Задержка: {camp['delay_min']}–{camp['delay_max']} сек\n"
        f"В час: {camp['hourly_limit']}\n"
        f"В день: {camp['daily_limit']}"
    )
    await callback.message.edit_text(
        text, reply_markup=campaign_item_kb(camp_id, bool(camp["is_active"])),
        parse_mode="HTML",
    )


# --- Режим кампании ---

@router.callback_query(F.data.startswith("camp_mode_"))
async def camp_mode(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one(
        "SELECT * FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return
    current_mode = camp["mode"] or "comments"
    labels = [MODE_LABELS.get(m, m) for m in current_mode.split(",")]
    await callback.message.edit_text(
        f"🎯 <b>Режимы кампании «{camp['name']}»</b>\n\n"
        f"Выбрано: {', '.join(labels)}\n\n"
        f"Можно выбрать несколько режимов одновременно.",
        reply_markup=camp_mode_kb(camp_id, current_mode),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("camp_setmode_"))
async def camp_setmode(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split("_")
    camp_id = int(parts[2])
    toggled_mode = "_".join(parts[3:])

    # Мультивыбор: переключаем режим вкл/выкл
    camp = await fetch_one(
        "SELECT mode FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    current_modes = set((camp["mode"] or "comments").split(","))

    if toggled_mode in current_modes:
        current_modes.discard(toggled_mode)
    else:
        current_modes.add(toggled_mode)

    # Не допускаем пустой набор режимов
    if not current_modes:
        await callback.answer("Нужен хотя бы один режим", show_alert=True)
        return

    new_mode = ",".join(sorted(current_modes, key=lambda m: list(MODE_LABELS.keys()).index(m)
                                if m in MODE_LABELS else 99))
    await execute("UPDATE campaigns SET mode = ? WHERE id = ?", (new_mode, camp_id))

    labels = [MODE_LABELS.get(m, m) for m in new_mode.split(",")]
    await callback.answer(f"✅ Режимы: {', '.join(labels)}")

    await callback.message.edit_reply_markup(
        reply_markup=camp_mode_kb(camp_id, new_mode))


# --- Привязка каналов ---

@router.callback_query(F.data.startswith("camp_channels_"))
async def camp_channels(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    channels = await fetch_all(
        "SELECT id, username FROM channels WHERE owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    linked = await fetch_all(
        "SELECT channel_id FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["channel_id"] for r in linked}

    if not channels:
        await callback.answer("Сначала добавьте каналы", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 Выберите каналы для кампании:",
        reply_markup=camp_select_items_kb(channels, "camp_ch", camp_id, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("camp_ch_toggle_"))
async def camp_ch_toggle(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split("_")
    camp_id = int(parts[3])
    ch_id = int(parts[4])

    existing = await fetch_one(
        "SELECT 1 FROM campaign_channels WHERE campaign_id = ? AND channel_id = ?",
        (camp_id, ch_id))
    if existing:
        await execute(
            "DELETE FROM campaign_channels WHERE campaign_id = ? AND channel_id = ?",
            (camp_id, ch_id))
    else:
        await execute(
            "INSERT INTO campaign_channels (campaign_id, channel_id) VALUES (?, ?)",
            (camp_id, ch_id))

    channels = await fetch_all(
        "SELECT id, username FROM channels WHERE owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    linked = await fetch_all(
        "SELECT channel_id FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["channel_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=camp_select_items_kb(channels, "camp_ch", camp_id, selected_ids))
    await callback.answer()


# --- Привязка аккаунтов ---

@router.callback_query(F.data.startswith("camp_accounts_"))
async def camp_accounts(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    accounts = await fetch_all(
        "SELECT id, phone FROM accounts WHERE status = 'active' AND owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    linked = await fetch_all(
        "SELECT account_id FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["account_id"] for r in linked}

    if not accounts:
        await callback.answer("Нет активных аккаунтов", show_alert=True)
        return

    await callback.message.edit_text(
        "📱 Выберите аккаунты для кампании:",
        reply_markup=camp_select_items_kb(accounts, "camp_acc", camp_id, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("camp_acc_toggle_"))
async def camp_acc_toggle(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split("_")
    camp_id = int(parts[3])
    acc_id = int(parts[4])

    existing = await fetch_one(
        "SELECT 1 FROM campaign_accounts WHERE campaign_id = ? AND account_id = ?",
        (camp_id, acc_id))
    if existing:
        await execute(
            "DELETE FROM campaign_accounts WHERE campaign_id = ? AND account_id = ?",
            (camp_id, acc_id))
    else:
        await execute(
            "INSERT INTO campaign_accounts (campaign_id, account_id) VALUES (?, ?)",
            (camp_id, acc_id))

    accounts = await fetch_all(
        "SELECT id, phone FROM accounts WHERE status = 'active' AND owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    linked = await fetch_all(
        "SELECT account_id FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["account_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=camp_select_items_kb(accounts, "camp_acc", camp_id, selected_ids))
    await callback.answer()


# --- Привязка сообщений ---

@router.callback_query(F.data.startswith("camp_messages_"))
async def camp_messages(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    messages = await fetch_all(
        "SELECT id, text FROM messages WHERE is_active = 1 AND owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    linked = await fetch_all(
        "SELECT message_id FROM campaign_messages WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["message_id"] for r in linked}

    if not messages:
        await callback.answer("Сначала добавьте сообщения", show_alert=True)
        return

    await callback.message.edit_text(
        "💬 Выберите сообщения для кампании:",
        reply_markup=camp_select_items_kb(messages, "camp_msg", camp_id, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("camp_msg_toggle_"))
async def camp_msg_toggle(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split("_")
    camp_id = int(parts[3])
    msg_id = int(parts[4])

    existing = await fetch_one(
        "SELECT 1 FROM campaign_messages WHERE campaign_id = ? AND message_id = ?",
        (camp_id, msg_id))
    if existing:
        await execute(
            "DELETE FROM campaign_messages WHERE campaign_id = ? AND message_id = ?",
            (camp_id, msg_id))
    else:
        await execute(
            "INSERT INTO campaign_messages (campaign_id, message_id) VALUES (?, ?)",
            (camp_id, msg_id))

    messages = await fetch_all(
        "SELECT id, text FROM messages WHERE is_active = 1 AND owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    linked = await fetch_all(
        "SELECT message_id FROM campaign_messages WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["message_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=camp_select_items_kb(messages, "camp_msg", camp_id, selected_ids))
    await callback.answer()


# --- Лимиты ---

@router.callback_query(F.data.startswith("camp_limits_"))
async def camp_limits(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one(
        "SELECT * FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    text = (
        f"⚙️ <b>Лимиты кампании «{camp['name']}»</b>\n\n"
        f"⏱ Мин. задержка: {camp['delay_min']} сек\n"
        f"⏱ Макс. задержка: {camp['delay_max']} сек\n"
        f"🕐 Лимит/час: {camp['hourly_limit']}\n"
        f"📅 Лимит/день: {camp['daily_limit']}"
    )
    await callback.message.edit_text(text, reply_markup=camp_limits_kb(camp_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("camp_set_"))
async def camp_set_limit(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    # camp_set_delay_min_1, camp_set_delay_max_1, camp_set_hourly_1, camp_set_daily_1
    camp_id = int(parts[-1])
    field = "_".join(parts[2:-1])  # delay_min, delay_max, hourly, daily

    field_map = {
        "delay_min": ("delay_min", "минимальную задержку (сек)"),
        "delay_max": ("delay_max", "максимальную задержку (сек)"),
        "hourly": ("hourly_limit", "лимит комментариев в час"),
        "daily": ("daily_limit", "лимит комментариев в день"),
    }
    db_field, label = field_map[field]

    await state.set_state(SetLimit.value)
    await state.update_data(camp_id=camp_id, db_field=db_field)
    await callback.message.edit_text(f"✏️ Введите {label}:")
    await callback.answer()


@router.message(SetLimit.value)
async def camp_set_limit_value(message: Message, state: FSMContext, db_user: dict):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите число:")
        return
    value = int(message.text.strip())
    data = await state.get_data()
    await state.clear()

    await execute(
        f"UPDATE campaigns SET {data['db_field']} = ? WHERE id = ? AND owner_user_id = ?",
        (value, data["camp_id"], db_user["telegram_id"]),
    )
    await message.answer(
        f"✅ Значение обновлено.",
        reply_markup=camp_limits_kb(data["camp_id"]),
    )


# --- Удаление ---

@router.callback_query(F.data.startswith("camp_del_confirm_"))
async def camp_del_confirm(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[3])
    camp = await fetch_one(
        "SELECT id FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return
    await execute("UPDATE logs SET campaign_id = NULL WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_messages WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaigns WHERE id = ?", (camp_id,))
    await callback.message.edit_text("✅ Кампания удалена.", reply_markup=campaigns_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("camp_del_"))
async def camp_del(callback: CallbackQuery, db_user: dict):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one(
        "SELECT name FROM campaigns WHERE id = ? AND owner_user_id = ?",
        (camp_id, db_user["telegram_id"]))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑 Удалить кампанию «{camp['name']}»?",
        reply_markup=camp_confirm_del_kb(camp_id),
    )
    await callback.answer()


# --- Логи кампании ---

LOGS_PER_PAGE = 15

@router.callback_query(F.data.regexp(r"^camp_logs_(\d+)(_p(\d+))?$"))
async def camp_logs(callback: CallbackQuery):
    import re
    match = re.match(r"^camp_logs_(\d+)(?:_p(\d+))?$", callback.data)
    camp_id = int(match.group(1))
    page = int(match.group(2)) if match.group(2) else 0

    camp = await fetch_one("SELECT name FROM campaigns WHERE id = ?", (camp_id,))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return

    # Общая статистика
    total = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE campaign_id = ?", (camp_id,))
    sent = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE campaign_id = ? AND status = 'sent'",
        (camp_id,))
    errors = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE campaign_id = ? AND status = 'error'",
        (camp_id,))

    total_count = total["cnt"]
    total_pages = max(1, (total_count + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE)
    if page >= total_pages:
        page = total_pages - 1

    offset = page * LOGS_PER_PAGE
    logs = await fetch_all(
        "SELECT l.*, a.phone, c.username "
        "FROM logs l "
        "LEFT JOIN accounts a ON l.account_id = a.id "
        "LEFT JOIN channels c ON l.channel_id = c.id "
        "WHERE l.campaign_id = ? "
        "ORDER BY l.sent_at DESC LIMIT ? OFFSET ?",
        (camp_id, LOGS_PER_PAGE, offset),
    )

    mode_icons = {
        "comments": "💬",
        "subscribe": "📥",
        "stories": "👁",
        "stories_like": "❤️",
        "dm": "✉️",
    }

    lines = [
        f"📊 <b>Логи: {camp['name']}</b>\n",
        f"Всего: {total_count}  |  ✅ {sent['cnt']}  |  ❌ {errors['cnt']}\n",
    ]

    if not logs:
        lines.append("Логов пока нет.")
    else:
        for log in logs:
            icon = mode_icons.get(log["mode"], "❓")
            status_icon = "✅" if log["status"] == "sent" else "❌"
            phone = log["phone"] or "—"
            channel = f"@{log['username']}" if log["username"] else "—"
            time_str = log["sent_at"][11:16] if log["sent_at"] and len(log["sent_at"]) > 16 else log["sent_at"] or "—"
            date_str = log["sent_at"][:10] if log["sent_at"] and len(log["sent_at"]) >= 10 else ""

            if log["mode"] == "dm" and log["target_user_id"]:
                target = f"<a href=\"tg://user?id={log['target_user_id']}\">профиль</a> ({channel})"
            else:
                target = channel
            line = f"{status_icon}{icon} {phone} → {target}  {date_str} {time_str}"
            if log["error"]:
                err_short = log["error"][:60]
                line += f"\n     <i>{err_short}</i>"
            lines.append(line)

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n…"

    await callback.message.edit_text(
        text,
        reply_markup=camp_logs_kb(camp_id, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()
