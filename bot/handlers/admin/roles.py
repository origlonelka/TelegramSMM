"""Admin role management (superadmin only)."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from services.audit import log_action

router = Router()


class AddAdmin(StatesGroup):
    user_id = State()


ROLE_OPTIONS = ["admin", "finance", "support"]


@router.callback_query(F.data == "adm_roles")
async def roles_menu(callback: CallbackQuery, admin: dict):
    if admin["role"] != "superadmin":
        await callback.answer("Только для суперадминов", show_alert=True)
        return
    admins = await fetch_all(
        "SELECT user_id, username, role, is_active FROM admins ORDER BY id")
    lines = ["🛡 <b>Управление админами</b>\n"]
    for a in admins:
        status = "🟢" if a["is_active"] else "🔴"
        name = f"@{a['username']}" if a["username"] else str(a["user_id"])
        lines.append(f"{status} {name} — {a['role']}")
    text = "\n".join(lines)
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="adm_role_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
        ]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_role_add")
async def role_add_start(callback: CallbackQuery, state: FSMContext, admin: dict):
    if admin["role"] != "superadmin":
        await callback.answer("Только для суперадминов", show_alert=True)
        return
    await state.set_state(AddAdmin.user_id)
    await callback.message.edit_text(
        "Введите Telegram ID нового админа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm_roles")],
        ]))
    await callback.answer()


@router.message(AddAdmin.user_id)
async def role_add_id(message: Message, state: FSMContext, admin: dict):
    if admin["role"] != "superadmin":
        await state.clear()
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("Некорректный ID. Попробуйте ещё раз.")
        return
    await state.clear()
    existing = await fetch_one("SELECT id FROM admins WHERE user_id = ?", (uid,))
    if existing:
        await message.answer("Этот пользователь уже админ.")
        return

    await execute_returning(
        "INSERT INTO admins (user_id, role, added_by) VALUES (?, 'admin', ?)",
        (uid, admin["user_id"]))
    await log_action(admin["user_id"], "admin_added", "admin", uid)
    await message.answer(f"✅ Админ {uid} добавлен с ролью admin.")


@router.callback_query(F.data.startswith("adm_role_set_"))
async def role_set(callback: CallbackQuery, admin: dict):
    if admin["role"] != "superadmin":
        await callback.answer("Только для суперадминов", show_alert=True)
        return
    parts = callback.data.split("_")
    uid = int(parts[3])
    new_role = parts[4]
    if new_role not in ROLE_OPTIONS:
        await callback.answer("Неверная роль", show_alert=True)
        return
    await execute("UPDATE admins SET role = ? WHERE user_id = ?", (new_role, uid))
    await log_action(admin["user_id"], "admin_role_changed", "admin", uid,
                     {"new_role": new_role})
    await callback.answer(f"Роль изменена на {new_role}")


@router.callback_query(F.data.startswith("adm_role_toggle_"))
async def role_toggle(callback: CallbackQuery, admin: dict):
    if admin["role"] != "superadmin":
        await callback.answer("Только для суперадминов", show_alert=True)
        return
    uid = int(callback.data.replace("adm_role_toggle_", ""))
    a = await fetch_one("SELECT is_active FROM admins WHERE user_id = ?", (uid,))
    if not a:
        await callback.answer("Админ не найден", show_alert=True)
        return
    new_status = 0 if a["is_active"] else 1
    await execute("UPDATE admins SET is_active = ? WHERE user_id = ?", (new_status, uid))
    await log_action(admin["user_id"], "admin_toggled", "admin", uid,
                     {"is_active": new_status})
    await callback.answer("Статус изменён")
