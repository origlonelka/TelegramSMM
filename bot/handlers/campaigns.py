from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    campaigns_menu_kb, campaign_list_kb, campaign_item_kb,
    camp_confirm_del_kb, camp_select_items_kb, camp_limits_kb, back_kb,
    camp_mode_kb, MODE_LABELS,
)

router = Router()


class AddCampaign(StatesGroup):
    name = State()


class SetLimit(StatesGroup):
    value = State()


# --- Меню кампаний ---

@router.callback_query(F.data.in_({"campaigns", "back_campaigns"}))
async def campaigns_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    count = await fetch_one("SELECT COUNT(*) as cnt FROM campaigns")
    text = f"🚀 <b>Кампании</b>\n\nВсего: {count['cnt']}"
    await callback.message.edit_text(text, reply_markup=campaigns_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "camp_list")
async def camp_list(callback: CallbackQuery):
    campaigns = await fetch_all("SELECT id, name, is_active FROM campaigns ORDER BY id")
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
async def camp_view(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one("SELECT * FROM campaigns WHERE id = ?", (camp_id,))
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
    mode_label = MODE_LABELS.get(mode, mode)
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
async def camp_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.clear()
    camp_id = await execute_returning(
        "INSERT INTO campaigns (name) VALUES (?)", (name,)
    )
    await message.answer(
        f"✅ Кампания «{name}» создана (#{camp_id}).\n"
        f"Теперь добавьте каналы, аккаунты и сообщения.",
        reply_markup=campaign_item_kb(camp_id, False),
    )


# --- Вкл/Выкл ---

@router.callback_query(F.data.startswith("camp_toggle_"))
async def camp_toggle(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one("SELECT is_active FROM campaigns WHERE id = ?", (camp_id,))
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
    mode_label = MODE_LABELS.get(mode, mode)
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
async def camp_mode(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one("SELECT * FROM campaigns WHERE id = ?", (camp_id,))
    if not camp:
        await callback.answer("Кампания не найдена", show_alert=True)
        return
    current_mode = camp["mode"] or "comments"
    await callback.message.edit_text(
        f"🎯 <b>Режим кампании «{camp['name']}»</b>\n\n"
        f"Текущий: {MODE_LABELS.get(current_mode, current_mode)}\n\n"
        f"💬 <b>Комментарии</b> — оставляет комментарии под постами\n"
        f"💬 <b>Комментарии + CTA</b> — комментарии с мягкой рекламой\n"
        f"👁 <b>Просмотр Stories</b> — просматривает Stories каналов\n"
        f"📢 <b>Подписка + просмотр</b> — подписка на каналы и просмотр постов",
        reply_markup=camp_mode_kb(camp_id, current_mode),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("camp_setmode_"))
async def camp_setmode(callback: CallbackQuery):
    parts = callback.data.split("_")
    camp_id = int(parts[2])
    mode = "_".join(parts[3:])  # comments, comments_cta, stories, subscribe

    await execute("UPDATE campaigns SET mode = ? WHERE id = ?", (mode, camp_id))
    await callback.answer(f"✅ Режим: {MODE_LABELS.get(mode, mode)}")

    camp = await fetch_one("SELECT * FROM campaigns WHERE id = ?", (camp_id,))
    current_mode = camp["mode"] or "comments"
    await callback.message.edit_text(
        f"🎯 <b>Режим кампании «{camp['name']}»</b>\n\n"
        f"Текущий: {MODE_LABELS.get(current_mode, current_mode)}\n\n"
        f"💬 <b>Комментарии</b> — оставляет комментарии под постами\n"
        f"💬 <b>Комментарии + CTA</b> — комментарии с мягкой рекламой\n"
        f"👁 <b>Просмотр Stories</b> — просматривает Stories каналов\n"
        f"📢 <b>Подписка + просмотр</b> — подписка на каналы и просмотр постов",
        reply_markup=camp_mode_kb(camp_id, current_mode),
        parse_mode="HTML",
    )


# --- Привязка каналов ---

@router.callback_query(F.data.startswith("camp_channels_"))
async def camp_channels(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    channels = await fetch_all("SELECT id, username FROM channels ORDER BY id")
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
async def camp_ch_toggle(callback: CallbackQuery):
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

    channels = await fetch_all("SELECT id, username FROM channels ORDER BY id")
    linked = await fetch_all(
        "SELECT channel_id FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["channel_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=camp_select_items_kb(channels, "camp_ch", camp_id, selected_ids))
    await callback.answer()


# --- Привязка аккаунтов ---

@router.callback_query(F.data.startswith("camp_accounts_"))
async def camp_accounts(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    accounts = await fetch_all("SELECT id, phone FROM accounts WHERE status = 'active' ORDER BY id")
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
async def camp_acc_toggle(callback: CallbackQuery):
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

    accounts = await fetch_all("SELECT id, phone FROM accounts WHERE status = 'active' ORDER BY id")
    linked = await fetch_all(
        "SELECT account_id FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["account_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=camp_select_items_kb(accounts, "camp_acc", camp_id, selected_ids))
    await callback.answer()


# --- Привязка сообщений ---

@router.callback_query(F.data.startswith("camp_messages_"))
async def camp_messages(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    messages = await fetch_all("SELECT id, text FROM messages WHERE is_active = 1 ORDER BY id")
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
async def camp_msg_toggle(callback: CallbackQuery):
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

    messages = await fetch_all("SELECT id, text FROM messages WHERE is_active = 1 ORDER BY id")
    linked = await fetch_all(
        "SELECT message_id FROM campaign_messages WHERE campaign_id = ?", (camp_id,))
    selected_ids = {r["message_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=camp_select_items_kb(messages, "camp_msg", camp_id, selected_ids))
    await callback.answer()


# --- Лимиты ---

@router.callback_query(F.data.startswith("camp_limits_"))
async def camp_limits(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one("SELECT * FROM campaigns WHERE id = ?", (camp_id,))
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
async def camp_set_limit_value(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите число:")
        return
    value = int(message.text.strip())
    data = await state.get_data()
    await state.clear()

    await execute(
        f"UPDATE campaigns SET {data['db_field']} = ? WHERE id = ?",
        (value, data["camp_id"]),
    )
    await message.answer(
        f"✅ Значение обновлено.",
        reply_markup=camp_limits_kb(data["camp_id"]),
    )


# --- Удаление ---

@router.callback_query(F.data.startswith("camp_del_confirm_"))
async def camp_del_confirm(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[3])
    await execute("DELETE FROM campaigns WHERE id = ?", (camp_id,))
    await execute("DELETE FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_messages WHERE campaign_id = ?", (camp_id,))
    await callback.message.edit_text("✅ Кампания удалена.", reply_markup=campaigns_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("camp_del_"))
async def camp_del(callback: CallbackQuery):
    camp_id = int(callback.data.split("_")[2])
    camp = await fetch_one("SELECT name FROM campaigns WHERE id = ?", (camp_id,))
    await callback.message.edit_text(
        f"🗑 Удалить кампанию «{camp['name']}»?",
        reply_markup=camp_confirm_del_kb(camp_id),
    )
    await callback.answer()
