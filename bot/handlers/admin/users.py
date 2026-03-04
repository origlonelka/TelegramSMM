"""Admin user management: search, block, unblock, manual subscription."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, fetch_one, fetch_all
from services.user_manager import block_user, unblock_user
from services.audit import log_action

router = Router()

ROLE_HIERARCHY = {"superadmin": 4, "admin": 3, "finance": 2, "support": 1}


class SearchUser(StatesGroup):
    query = State()


def _check_role(admin: dict, min_role: str = "admin") -> bool:
    return ROLE_HIERARCHY.get(admin["role"], 0) >= ROLE_HIERARCHY.get(min_role, 99)


def user_info_kb(tg_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "blocked":
        buttons.append([InlineKeyboardButton(
            text="🔓 Разблокировать", callback_data=f"adm_user_unblock_{tg_id}")])
    else:
        buttons.append([InlineKeyboardButton(
            text="🔒 Заблокировать", callback_data=f"adm_user_block_{tg_id}")])
    buttons.append([InlineKeyboardButton(
        text="🔄 Сбросить trial", callback_data=f"adm_user_reset_trial_{tg_id}")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data="adm_users")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.in_({"adm_users", "adm_user_search"}))
async def users_menu(callback: CallbackQuery, state: FSMContext, admin: dict):
    if not _check_role(admin, "admin"):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.set_state(SearchUser.query)
    total = await fetch_one("SELECT COUNT(*) as c FROM users")
    text = (
        "👤 <b>Управление пользователями</b>\n\n"
        f"Всего пользователей: {total['c']}\n\n"
        "🔍 Введите Telegram ID или @username для поиска:"
    )
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
        ]), parse_mode="HTML")
    await callback.answer()


@router.message(SearchUser.query)
async def user_search(message: Message, state: FSMContext):
    await state.clear()
    q = message.text.strip().lstrip("@")

    # Search by ID or username
    try:
        tg_id = int(q)
        user = await fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    except ValueError:
        user = await fetch_one(
            "SELECT * FROM users WHERE username = ?", (q,))

    if not user:
        await message.answer("Пользователь не найден.")
        return

    await _show_user_info(message, dict(user))


async def _show_user_info(target, user: dict):
    """Show user info (works with both Message and CallbackQuery)."""
    subs = await fetch_all(
        "SELECT s.*, p.name as plan_name FROM subscriptions s "
        "LEFT JOIN subscription_plans p ON s.plan_id = p.id "
        "WHERE s.user_telegram_id = ? ORDER BY s.created_at DESC LIMIT 3",
        (user["telegram_id"],))

    sub_lines = ""
    for s in subs:
        sub_lines += f"\n  {s['plan_name'] or '?'}: {s['status']} ({s['expires_at'] or '—'})"

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"ID: <code>{user['telegram_id']}</code>\n"
        f"Username: @{user['username'] or '—'}\n"
        f"Имя: {user['first_name'] or '—'}\n"
        f"Статус: <b>{user['status']}</b>\n"
        f"Создан: {user['created_at']}\n"
        f"Trial: {user['trial_started_at'] or 'не начат'}"
        f"\n\n📦 Подписки:{sub_lines or ' нет'}"
    )

    kb = user_info_kb(user["telegram_id"], user["status"])
    if hasattr(target, 'edit_text'):
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_user_block_"))
async def user_block(callback: CallbackQuery, admin: dict):
    if not _check_role(admin, "admin"):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    tg_id = int(callback.data.replace("adm_user_block_", ""))
    await block_user(tg_id)
    await log_action(admin["user_id"], "user_blocked", "user", tg_id)
    await callback.answer("Пользователь заблокирован")
    user = await fetch_one("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    if user:
        await _show_user_info(callback.message, dict(user))


@router.callback_query(F.data.startswith("adm_user_unblock_"))
async def user_unblock(callback: CallbackQuery, admin: dict):
    if not _check_role(admin, "admin"):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    tg_id = int(callback.data.replace("adm_user_unblock_", ""))
    await unblock_user(tg_id)
    await log_action(admin["user_id"], "user_unblocked", "user", tg_id)
    await callback.answer("Пользователь разблокирован")
    user = await fetch_one("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    if user:
        await _show_user_info(callback.message, dict(user))


@router.callback_query(F.data.startswith("adm_user_reset_trial_"))
async def user_reset_trial(callback: CallbackQuery, admin: dict):
    if admin["role"] != "superadmin":
        await callback.answer("Только для суперадминов", show_alert=True)
        return
    tg_id = int(callback.data.replace("adm_user_reset_trial_", ""))
    await execute(
        "UPDATE users SET trial_started_at = NULL, trial_expires_at = NULL, "
        "status = 'new', updated_at = datetime('now') WHERE telegram_id = ?",
        (tg_id,))
    await log_action(admin["user_id"], "trial_reset", "user", tg_id)
    await callback.answer("Trial сброшен")
    user = await fetch_one("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    if user:
        await _show_user_info(callback.message, dict(user))
