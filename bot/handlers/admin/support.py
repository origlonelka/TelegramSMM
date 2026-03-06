"""Admin support tickets: list, view, reply, close."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, fetch_all, fetch_one
from services.audit import log_action

router = Router()


class ReplyTicket(StatesGroup):
    text = State()


@router.callback_query(F.data == "adm_tickets")
async def tickets_menu(callback: CallbackQuery, admin: dict):
    open_tickets = await fetch_all(
        "SELECT t.*, u.username FROM support_tickets t "
        "LEFT JOIN users u ON t.user_telegram_id = u.telegram_id "
        "WHERE t.status = 'open' ORDER BY t.created_at DESC LIMIT 20")
    lines = ["🎫 <b>Тикеты поддержки</b>\n"]
    buttons = []
    if not open_tickets:
        lines.append("Нет открытых тикетов.")
    else:
        for t in open_tickets:
            name = f"@{t['username']}" if t["username"] else str(t["user_telegram_id"])
            subj = t["subject"] or "Без темы"
            lines.append(f"#{t['id']} {name}: {subj}")
            buttons.append([InlineKeyboardButton(
                text=f"#{t['id']} {subj[:30]}",
                callback_data=f"adm_ticket_{t['id']}")])

    buttons.append([InlineKeyboardButton(text="📦 Закрытые", callback_data="adm_tickets_closed")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_tickets_closed")
async def tickets_closed(callback: CallbackQuery, admin: dict):
    closed = await fetch_all(
        "SELECT t.*, u.username FROM support_tickets t "
        "LEFT JOIN users u ON t.user_telegram_id = u.telegram_id "
        "WHERE t.status = 'closed' ORDER BY t.updated_at DESC LIMIT 20")
    lines = ["📦 <b>Закрытые тикеты</b>\n"]
    if not closed:
        lines.append("Нет закрытых тикетов.")
    else:
        for t in closed:
            name = f"@{t['username']}" if t["username"] else str(t["user_telegram_id"])
            subj = t["subject"] or "Без темы"
            lines.append(f"#{t['id']} {name}: {subj}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_tickets")],
        ]),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_ticket_reply_"))
async def ticket_reply_start(callback: CallbackQuery, state: FSMContext, admin: dict):
    ticket_id = int(callback.data.replace("adm_ticket_reply_", ""))
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(ReplyTicket.text)
    await callback.message.edit_text(
        f"Введите ответ на тикет #{ticket_id}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm_ticket_{ticket_id}")],
        ]))
    await callback.answer()


@router.message(ReplyTicket.text)
async def ticket_reply_send(message: Message, state: FSMContext, admin: dict):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    await state.clear()

    ticket = await fetch_one(
        "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        await message.answer("Тикет не найден.")
        return

    await execute(
        "INSERT INTO ticket_messages (ticket_id, sender_telegram_id, text, is_admin) "
        "VALUES (?, ?, ?, 1)",
        (ticket_id, admin["user_id"], message.text.strip()))
    await execute(
        "UPDATE support_tickets SET updated_at = datetime('now') WHERE id = ?",
        (ticket_id,))
    await log_action(admin["user_id"], "ticket_replied", "ticket", ticket_id)

    # Notify user
    try:
        from core.webhook_server import _bot_instance
        if _bot_instance:
            await _bot_instance.send_message(
                chat_id=ticket["user_telegram_id"],
                text=f"💬 <b>Ответ на тикет #{ticket_id}</b>\n\n{message.text.strip()}",
                parse_mode="HTML")
    except Exception:
        pass

    await message.answer(f"✅ Ответ отправлен в тикет #{ticket_id}.")


@router.callback_query(F.data.startswith("adm_ticket_close_"))
async def ticket_close(callback: CallbackQuery, admin: dict):
    ticket_id = int(callback.data.replace("adm_ticket_close_", ""))
    await execute(
        "UPDATE support_tickets SET status = 'closed', updated_at = datetime('now') "
        "WHERE id = ?", (ticket_id,))
    await log_action(admin["user_id"], "ticket_closed", "ticket", ticket_id)
    await callback.answer("Тикет закрыт")
    await tickets_menu(callback, admin)


@router.callback_query(F.data.startswith("adm_ticket_"))
async def ticket_view(callback: CallbackQuery, admin: dict):
    ticket_id = int(callback.data.replace("adm_ticket_", ""))
    ticket = await fetch_one(
        "SELECT t.*, u.username FROM support_tickets t "
        "LEFT JOIN users u ON t.user_telegram_id = u.telegram_id "
        "WHERE t.id = ?", (ticket_id,))
    if not ticket:
        await callback.answer("Тикет не найден", show_alert=True)
        return

    messages = await fetch_all(
        "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at",
        (ticket_id,))

    name = f"@{ticket['username']}" if ticket["username"] else str(ticket["user_telegram_id"])
    lines = [
        f"🎫 <b>Тикет #{ticket['id']}</b>\n",
        f"От: {name}",
        f"Тема: {ticket['subject'] or 'Без темы'}",
        f"Статус: {ticket['status']}",
        f"Создан: {ticket['created_at']}\n",
        "💬 <b>Сообщения:</b>",
    ]
    for m in messages:
        sender = "🛡 Админ" if m["is_admin"] else "👤 Пользователь"
        lines.append(f"\n{sender} ({m['created_at'][:16]}):\n{m['text']}")

    buttons = []
    if ticket["status"] == "open":
        buttons.append([InlineKeyboardButton(
            text="💬 Ответить", callback_data=f"adm_ticket_reply_{ticket_id}")])
        buttons.append([InlineKeyboardButton(
            text="✅ Закрыть", callback_data=f"adm_ticket_close_{ticket_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_tickets")])

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()
