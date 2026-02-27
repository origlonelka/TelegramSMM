from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    messages_menu_kb, message_list_kb, message_item_kb,
    msg_confirm_del_kb, back_kb,
)

router = Router()


class AddMessage(StatesGroup):
    text = State()


# --- Меню сообщений ---

@router.callback_query(F.data == "messages")
async def messages_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    count = await fetch_one("SELECT COUNT(*) as cnt FROM messages")
    text = f"💬 <b>Шаблоны сообщений</b>\n\nВсего: {count['cnt']}"
    await callback.message.edit_text(text, reply_markup=messages_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "msg_list")
async def msg_list(callback: CallbackQuery):
    messages = await fetch_all("SELECT id, text, is_active FROM messages ORDER BY id")
    if not messages:
        await callback.answer("Список пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Список сообщений:</b>",
        reply_markup=message_list_kb(messages),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр ---

@router.callback_query(F.data.startswith("msg_view_"))
async def msg_view(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[2])
    msg = await fetch_one("SELECT * FROM messages WHERE id = ?", (msg_id,))
    if not msg:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return
    status = "🟢 Активно" if msg["is_active"] else "🔴 Выключено"
    text = (
        f"💬 <b>Сообщение #{msg['id']}</b>\n\n"
        f"Статус: {status}\n"
        f"Создано: {msg['created_at']}\n\n"
        f"<b>Текст:</b>\n<code>{msg['text']}</code>"
    )
    await callback.message.edit_text(
        text, reply_markup=message_item_kb(msg_id, bool(msg["is_active"])),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Добавление ---

@router.callback_query(F.data == "msg_add")
async def msg_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddMessage.text)
    await callback.message.edit_text(
        "💬 Введите текст рекламного сообщения:",
        reply_markup=back_kb("messages"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddMessage.text)
async def msg_add_text(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()

    msg_id = await execute_returning(
        "INSERT INTO messages (text) VALUES (?)", (text,)
    )
    await message.answer(
        f"✅ Сообщение добавлено (#{msg_id}).",
        reply_markup=message_item_kb(msg_id, True),
    )


# --- Вкл/Выкл ---

@router.callback_query(F.data.startswith("msg_toggle_"))
async def msg_toggle(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[2])
    msg = await fetch_one("SELECT is_active FROM messages WHERE id = ?", (msg_id,))
    new_status = 0 if msg["is_active"] else 1
    await execute("UPDATE messages SET is_active = ? WHERE id = ?", (new_status, msg_id))

    msg = await fetch_one("SELECT * FROM messages WHERE id = ?", (msg_id,))
    status = "🟢 Активно" if msg["is_active"] else "🔴 Выключено"
    text = (
        f"💬 <b>Сообщение #{msg['id']}</b>\n\n"
        f"Статус: {status}\n"
        f"Создано: {msg['created_at']}\n\n"
        f"<b>Текст:</b>\n<code>{msg['text']}</code>"
    )
    await callback.message.edit_text(
        text, reply_markup=message_item_kb(msg_id, bool(msg["is_active"])),
        parse_mode="HTML",
    )
    await callback.answer("✅ Статус изменён")


# --- Удаление ---

@router.callback_query(F.data.startswith("msg_del_confirm_"))
async def msg_del_confirm(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[3])
    await execute("DELETE FROM messages WHERE id = ?", (msg_id,))
    await callback.message.edit_text("✅ Сообщение удалено.", reply_markup=messages_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("msg_del_"))
async def msg_del(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        "🗑 Удалить это сообщение?",
        reply_markup=msg_confirm_del_kb(msg_id),
    )
    await callback.answer()
