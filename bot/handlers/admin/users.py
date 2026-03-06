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


class GrantSub(StatesGroup):
    days = State()


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
        text="💎 Выдать подписку", callback_data=f"adm_user_grant_sub_{tg_id}")])
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

    await _show_user_info(message, dict(user), edit=False)


async def _show_user_info(target, user: dict, edit: bool = True):
    """Show user info. edit=True → edit_text, edit=False → answer (new message)."""
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
    if edit:
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


@router.callback_query(F.data.startswith("adm_user_view_"))
async def user_view_by_id(callback: CallbackQuery, state: FSMContext, admin: dict):
    await state.clear()
    tg_id = int(callback.data.replace("adm_user_view_", ""))
    user = await fetch_one("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    await _show_user_info(callback.message, dict(user))
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_grant_sub_"))
async def user_grant_sub_start(callback: CallbackQuery, state: FSMContext, admin: dict):
    if not _check_role(admin, "admin"):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    tg_id = int(callback.data.replace("adm_user_grant_sub_", ""))
    await state.update_data(grant_tg_id=tg_id)
    await state.set_state(GrantSub.days)
    await callback.message.edit_text(
        f"💎 <b>Выдача подписки</b>\n\n"
        f"Пользователь: <code>{tg_id}</code>\n\n"
        f"Выберите срок или введите количество дней:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="7 дней", callback_data="adm_grant_days_7"),
             InlineKeyboardButton(text="30 дней", callback_data="adm_grant_days_30")],
            [InlineKeyboardButton(text="90 дней", callback_data="adm_grant_days_90"),
             InlineKeyboardButton(text="365 дней", callback_data="adm_grant_days_365")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm_user_view_{tg_id}")],
        ]),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_grant_days_"))
async def user_grant_sub_quick(callback: CallbackQuery, state: FSMContext, admin: dict):
    days = int(callback.data.replace("adm_grant_days_", ""))
    data = await state.get_data()
    tg_id = data.get("grant_tg_id")
    if not tg_id:
        await callback.answer("Ошибка, попробуйте заново", show_alert=True)
        return
    await state.clear()
    await _grant_subscription(callback.message, admin, tg_id, days)
    await callback.answer()


@router.message(GrantSub.days)
async def user_grant_sub_manual(message: Message, state: FSMContext, admin: dict):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Введите число дней (или нажмите кнопку).")
        return
    days = int(message.text.strip())
    if days < 1 or days > 3650:
        await message.answer("❌ Введите от 1 до 3650 дней.")
        return
    data = await state.get_data()
    tg_id = data.get("grant_tg_id")
    if not tg_id:
        await message.answer("Ошибка, попробуйте заново.")
        return
    await state.clear()
    await _grant_subscription(message, admin, tg_id, days, edit=False)


async def _grant_subscription(target, admin: dict, tg_id: int, days: int, edit: bool = True):
    """Grant free subscription to user."""
    current_sub = await fetch_one(
        "SELECT id, expires_at FROM subscriptions "
        "WHERE user_telegram_id = ? AND status = 'succeeded' "
        "AND expires_at > datetime('now') "
        "ORDER BY expires_at DESC LIMIT 1",
        (tg_id,))

    if current_sub:
        await execute(
            "UPDATE subscriptions SET "
            "expires_at = datetime(expires_at, '+' || ? || ' days') "
            "WHERE id = ?",
            (days, current_sub["id"]))
    else:
        await execute(
            "INSERT INTO subscriptions "
            "(user_telegram_id, plan_id, payment_id, status, amount_rub, "
            "started_at, expires_at) "
            "VALUES (?, 1, 'admin_grant_' || ? || '_' || ?, 'succeeded', 0, "
            "datetime('now'), datetime('now', '+' || ? || ' days'))",
            (tg_id, admin["user_id"], tg_id, days))

    await execute(
        "UPDATE users SET status = 'subscription_active', "
        "updated_at = datetime('now') WHERE telegram_id = ?",
        (tg_id,))
    await log_action(admin["user_id"], "subscription_granted", "user", tg_id,
                     f"{days} days")

    user = await fetch_one("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    if user:
        await _show_user_info(target, dict(user), edit=edit)
