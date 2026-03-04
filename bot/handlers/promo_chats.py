"""Promo chats management: add, list, remove, settings, link to campaigns."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one

router = Router()


class AddPromoChat(StatesGroup):
    username = State()


class SetChatLimit(StatesGroup):
    value = State()


# --- Keyboards ---

def promo_chats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить чат", callback_data="pchat_add")],
        [InlineKeyboardButton(text="📋 Список чатов", callback_data="pchat_list")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def promo_chat_item_kb(pchat_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить" if is_active else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"pchat_toggle_{pchat_id}")],
        [InlineKeyboardButton(text="⚙️ Лимиты", callback_data=f"pchat_limits_{pchat_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"pchat_del_{pchat_id}")],
        [InlineKeyboardButton(text="◀️ К чатам", callback_data="promo_chats")],
    ])


def pchat_limits_kb(pchat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ Мин. задержка", callback_data=f"pchat_set_min_delay_{pchat_id}"),
         InlineKeyboardButton(text="⏱ Макс. задержка", callback_data=f"pchat_set_max_delay_{pchat_id}")],
        [InlineKeyboardButton(text="🕐 Постов/час", callback_data=f"pchat_set_hour_{pchat_id}"),
         InlineKeyboardButton(text="📅 Постов/день", callback_data=f"pchat_set_day_{pchat_id}")],
        [InlineKeyboardButton(text="🔄 Дедуп (часов)", callback_data=f"pchat_set_dedup_{pchat_id}")],
        [InlineKeyboardButton(text="◀️ К чату", callback_data=f"pchat_view_{pchat_id}")],
    ])


# --- Menu ---

@router.callback_query(F.data.in_({"promo_chats", "back_promo_chats"}))
async def promo_chats_menu(callback: CallbackQuery, state: FSMContext, db_user: dict):
    await state.clear()
    count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM promo_chats WHERE owner_user_id = ?",
        (db_user["telegram_id"],))
    await callback.message.edit_text(
        f"📣 <b>Промо-чаты</b>\n\nВсего: {count['cnt']}",
        reply_markup=promo_chats_menu_kb(),
        parse_mode="HTML")
    await callback.answer()


# --- List ---

@router.callback_query(F.data == "pchat_list")
async def pchat_list(callback: CallbackQuery, db_user: dict):
    chats = await fetch_all(
        "SELECT id, username, title, is_active FROM promo_chats "
        "WHERE owner_user_id = ? ORDER BY id",
        (db_user["telegram_id"],))
    if not chats:
        await callback.answer("Список пуст", show_alert=True)
        return
    buttons = []
    for ch in chats:
        icon = "🟢" if ch["is_active"] else "🔴"
        label = f"@{ch['username']}" if ch["username"] else ch["title"] or f"#{ch['id']}"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {label}",
            callback_data=f"pchat_view_{ch['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ К чатам", callback_data="promo_chats")])
    await callback.message.edit_text(
        "📋 <b>Промо-чаты:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


# --- View ---

@router.callback_query(F.data.startswith("pchat_view_"))
async def pchat_view(callback: CallbackQuery, db_user: dict):
    pchat_id = int(callback.data.replace("pchat_view_", ""))
    chat = await fetch_one(
        "SELECT * FROM promo_chats WHERE id = ? AND owner_user_id = ?",
        (pchat_id, db_user["telegram_id"]))
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return
    status = "🟢 Активен" if chat["is_active"] else "🔴 Выключен"
    posting = "✅" if chat["allow_posting"] else "❌ (заблокирован)"
    label = f"@{chat['username']}" if chat["username"] else chat["title"] or "—"
    text = (
        f"📣 <b>Промо-чат: {label}</b>\n\n"
        f"Статус: {status}\n"
        f"Постинг: {posting}\n"
        f"Ошибок: {chat['error_count']}\n"
        f"Последний пост: {chat['last_post_at'] or '—'}\n\n"
        f"⚙️ <b>Лимиты:</b>\n"
        f"Задержка: {chat['min_delay']}–{chat['max_delay']} сек\n"
        f"Постов/час: {chat['max_posts_per_hour']}\n"
        f"Постов/день: {chat['max_posts_per_day']}\n"
        f"Дедуп: {chat['dedup_window_hours']} ч"
    )
    await callback.message.edit_text(
        text,
        reply_markup=promo_chat_item_kb(pchat_id, bool(chat["is_active"])),
        parse_mode="HTML")
    await callback.answer()


# --- Add ---

@router.callback_query(F.data == "pchat_add")
async def pchat_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPromoChat.username)
    await callback.message.edit_text(
        "Введите @username чата (без @):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="promo_chats")],
        ]))
    await callback.answer()


@router.message(AddPromoChat.username)
async def pchat_add_username(message: Message, state: FSMContext, db_user: dict):
    username = message.text.strip().lstrip("@")
    await state.clear()

    existing = await fetch_one(
        "SELECT id FROM promo_chats WHERE username = ? AND owner_user_id = ?",
        (username, db_user["telegram_id"]))
    if existing:
        await message.answer("Этот чат уже добавлен.")
        return

    pchat_id = await execute_returning(
        "INSERT INTO promo_chats (username, owner_user_id) VALUES (?, ?)",
        (username, db_user["telegram_id"]))
    await message.answer(
        f"✅ Промо-чат @{username} добавлен (#{pchat_id}).",
        reply_markup=promo_chat_item_kb(pchat_id, True))


# --- Toggle ---

@router.callback_query(F.data.startswith("pchat_toggle_"))
async def pchat_toggle(callback: CallbackQuery, db_user: dict):
    pchat_id = int(callback.data.replace("pchat_toggle_", ""))
    chat = await fetch_one(
        "SELECT is_active FROM promo_chats WHERE id = ? AND owner_user_id = ?",
        (pchat_id, db_user["telegram_id"]))
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return
    new_status = 0 if chat["is_active"] else 1
    await execute("UPDATE promo_chats SET is_active = ? WHERE id = ?",
                  (new_status, pchat_id))
    await callback.answer("Статус изменён")
    # Refresh view
    await pchat_view(callback, db_user)


# --- Delete ---

@router.callback_query(F.data.startswith("pchat_del_"))
async def pchat_del(callback: CallbackQuery, db_user: dict):
    pchat_id = int(callback.data.replace("pchat_del_", ""))
    await execute(
        "DELETE FROM campaign_promo_chats WHERE promo_chat_id = ?", (pchat_id,))
    await execute(
        "DELETE FROM promo_chats WHERE id = ? AND owner_user_id = ?",
        (pchat_id, db_user["telegram_id"]))
    await callback.answer("Чат удалён")
    await callback.message.edit_text(
        "✅ Промо-чат удалён.",
        reply_markup=promo_chats_menu_kb())


# --- Limits ---

@router.callback_query(F.data.startswith("pchat_limits_"))
async def pchat_limits(callback: CallbackQuery, db_user: dict):
    pchat_id = int(callback.data.replace("pchat_limits_", ""))
    chat = await fetch_one(
        "SELECT * FROM promo_chats WHERE id = ? AND owner_user_id = ?",
        (pchat_id, db_user["telegram_id"]))
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return
    text = (
        f"⚙️ <b>Лимиты промо-чата</b>\n\n"
        f"Мин. задержка: {chat['min_delay']} сек\n"
        f"Макс. задержка: {chat['max_delay']} сек\n"
        f"Постов/час: {chat['max_posts_per_hour']}\n"
        f"Постов/день: {chat['max_posts_per_day']}\n"
        f"Дедуп: {chat['dedup_window_hours']} ч"
    )
    await callback.message.edit_text(
        text, reply_markup=pchat_limits_kb(pchat_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("pchat_set_"))
async def pchat_set_limit(callback: CallbackQuery, state: FSMContext):
    # pchat_set_min_delay_1, pchat_set_hour_1, etc.
    parts = callback.data.split("_")
    pchat_id = int(parts[-1])
    field_key = "_".join(parts[2:-1])

    field_map = {
        "min_delay": ("min_delay", "минимальную задержку (сек)"),
        "max_delay": ("max_delay", "максимальную задержку (сек)"),
        "hour": ("max_posts_per_hour", "макс. постов в час"),
        "day": ("max_posts_per_day", "макс. постов в день"),
        "dedup": ("dedup_window_hours", "окно дедупликации (часов)"),
    }
    if field_key not in field_map:
        await callback.answer("Ошибка", show_alert=True)
        return
    db_field, label = field_map[field_key]

    await state.set_state(SetChatLimit.value)
    await state.update_data(pchat_id=pchat_id, db_field=db_field)
    await callback.message.edit_text(f"✏️ Введите {label}:")
    await callback.answer()


@router.message(SetChatLimit.value)
async def pchat_set_limit_value(message: Message, state: FSMContext, db_user: dict):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите число:")
        return
    value = int(message.text.strip())
    data = await state.get_data()
    await state.clear()

    await execute(
        f"UPDATE promo_chats SET {data['db_field']} = ? "
        f"WHERE id = ? AND owner_user_id = ?",
        (value, data["pchat_id"], db_user["telegram_id"]))
    await message.answer(
        "✅ Значение обновлено.",
        reply_markup=pchat_limits_kb(data["pchat_id"]))
