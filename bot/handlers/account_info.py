"""User account info: subscription status, referral system, support tickets, promo codes."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, fetch_one, fetch_all
from services.user_manager import get_or_create_user, check_entitlement

router = Router()

REFERRAL_BONUS_DAYS = 7


class CreateTicket(StatesGroup):
    subject = State()
    text = State()


class EnterPromo(StatesGroup):
    code = State()


def my_account_kb(has_active_sub: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if has_active_sub:
        buttons.append([InlineKeyboardButton(
            text="💳 Продлить подписку", callback_data="select_plan")])
    else:
        buttons.append([InlineKeyboardButton(
            text="💳 Купить подписку", callback_data="select_plan")])
    buttons.append([InlineKeyboardButton(
        text="🎟 Ввести промокод", callback_data="enter_promo")])
    buttons.append([InlineKeyboardButton(
        text="👥 Реферальная программа", callback_data="my_referrals")])
    buttons.append([InlineKeyboardButton(
        text="🎫 Поддержка", callback_data="my_tickets")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "my_account")
async def my_account(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = callback.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    tg_id = db_user["telegram_id"]
    ent = await check_entitlement(tg_id)

    # Subscription info
    status_labels = {
        "new": "Новый",
        "trial_active": "Пробный период",
        "subscription_active": "Активна",
        "expired": "Истекла",
        "blocked": "Заблокирован",
    }
    status_text = status_labels.get(ent["status"], ent["status"])

    # Get current subscription details
    sub = await fetch_one(
        "SELECT s.*, p.name as plan_name FROM subscriptions s "
        "LEFT JOIN subscription_plans p ON s.plan_id = p.id "
        "WHERE s.user_telegram_id = ? AND s.status = 'succeeded' "
        "AND s.expires_at > datetime('now') "
        "ORDER BY s.expires_at DESC LIMIT 1",
        (tg_id,))

    # Referral stats
    ref_count = await fetch_one(
        "SELECT COUNT(*) as c FROM referrals WHERE referrer_telegram_id = ?",
        (tg_id,))
    bonus_total = await fetch_one(
        "SELECT COALESCE(SUM(bonus_days), 0) as d FROM referrals "
        "WHERE referrer_telegram_id = ?",
        (tg_id,))

    text = "👤 <b>Мой аккаунт</b>\n\n"

    # Subscription section
    text += "<b>Подписка:</b>\n"
    text += f"Статус: {status_text}\n"
    if sub:
        text += f"Тариф: {sub['plan_name']}\n"
        if sub['expires_at']:
            text += f"Действует до: {sub['expires_at'][:16].replace('T', ' ')}\n"
    elif ent["status"] == "trial_active" and ent.get("expires_at"):
        text += f"Истекает: {ent['expires_at'][:16].replace('T', ' ')}\n"
    text += "\n"

    # Referral section
    bot_me = await callback.bot.get_me()
    bot_username = bot_me.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}"

    text += "<b>Реферальная программа:</b>\n"
    text += f"Приглашено: {ref_count['c']}\n"
    text += f"Бонусных дней: {bonus_total['d']}\n"
    if ref_link:
        text += f"\nВаша ссылка:\n<code>{ref_link}</code>\n"

    has_active = ent["status"] in ("subscription_active", "trial_active")
    await callback.message.edit_text(
        text, reply_markup=my_account_kb(has_active_sub=has_active),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "my_referrals")
async def my_referrals(callback: CallbackQuery):
    user = callback.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    tg_id = db_user["telegram_id"]

    # Referral link
    bot_me = await callback.bot.get_me()
    bot_username = bot_me.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}"

    # Get referred users
    referrals = await fetch_all(
        "SELECT r.referred_telegram_id, r.bonus_days, r.created_at, "
        "u.username, u.first_name "
        "FROM referrals r "
        "LEFT JOIN users u ON r.referred_telegram_id = u.telegram_id "
        "WHERE r.referrer_telegram_id = ? "
        "ORDER BY r.created_at DESC LIMIT 20",
        (tg_id,))

    ref_count = await fetch_one(
        "SELECT COUNT(*) as c FROM referrals WHERE referrer_telegram_id = ?",
        (tg_id,))
    bonus_total = await fetch_one(
        "SELECT COALESCE(SUM(bonus_days), 0) as d FROM referrals "
        "WHERE referrer_telegram_id = ?",
        (tg_id,))

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"За каждого приглашённого друга, который оплатит подписку, "
        f"вы получаете <b>{REFERRAL_BONUS_DAYS} дней</b> бесплатного доступа!\n\n"
    )

    if ref_link:
        text += f"Ваша ссылка:\n<code>{ref_link}</code>\n\n"

    text += (
        f"Всего приглашено: {ref_count['c']}\n"
        f"Бонусных дней получено: {bonus_total['d']}\n"
    )

    if referrals:
        text += "\n<b>Последние рефералы:</b>\n"
        for r in referrals:
            name = r["first_name"] or r["username"] or str(r["referred_telegram_id"])
            bonus = f" (+{r['bonus_days']}д)" if r["bonus_days"] else ""
            text += f"  {name}{bonus} — {r['created_at'][:10]}\n"

    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="◀️ Назад", callback_data="my_account")],
        ]), parse_mode="HTML")
    await callback.answer()


# --- Support tickets ---

@router.callback_query(F.data == "my_tickets")
async def my_tickets(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = callback.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    tg_id = db_user["telegram_id"]

    tickets = await fetch_all(
        "SELECT * FROM support_tickets WHERE user_telegram_id = ? "
        "ORDER BY created_at DESC LIMIT 10",
        (tg_id,))

    text = "🎫 <b>Мои тикеты</b>\n\n"
    buttons = []

    if tickets:
        for t in tickets:
            status_icon = "🟢" if t["status"] == "open" else "🔴"
            subj = t["subject"] or "Без темы"
            text += f"{status_icon} #{t['id']}: {subj} ({t['created_at'][:10]})\n"
            if t["status"] == "open":
                buttons.append([InlineKeyboardButton(
                    text=f"#{t['id']} {subj[:25]}",
                    callback_data=f"my_ticket_{t['id']}")])
    else:
        text += "У вас пока нет тикетов.\n"

    buttons.append([InlineKeyboardButton(
        text="➕ Создать тикет", callback_data="create_ticket")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data="my_account")])

    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("my_ticket_"))
async def my_ticket_view(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    ticket_id = int(callback.data.replace("my_ticket_", ""))
    ticket = await fetch_one(
        "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        await callback.answer("Тикет не найден", show_alert=True)
        return

    messages = await fetch_all(
        "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at",
        (ticket_id,))

    text = (
        f"🎫 <b>Тикет #{ticket['id']}</b>\n"
        f"Тема: {ticket['subject'] or 'Без темы'}\n"
        f"Статус: {ticket['status']}\n\n"
    )
    for m in messages:
        sender = "🛡 Поддержка" if m["is_admin"] else "👤 Вы"
        text += f"{sender} ({m['created_at'][:16]}):\n{m['text']}\n\n"

    if len(text) > 4000:
        text = text[:4000] + "\n..."

    buttons = []
    if ticket["status"] == "open":
        buttons.append([InlineKeyboardButton(
            text="💬 Ответить", callback_data=f"reply_ticket_{ticket_id}")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data="my_tickets")])

    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "create_ticket")
async def create_ticket_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateTicket.subject)
    await callback.message.edit_text(
        "🎫 <b>Создание тикета</b>\n\n"
        "Введите тему обращения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="my_tickets")],
        ]), parse_mode="HTML")
    await callback.answer()


@router.message(CreateTicket.subject)
async def create_ticket_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip()[:100])
    await state.set_state(CreateTicket.text)
    await message.answer(
        "Опишите вашу проблему или вопрос:")


@router.message(CreateTicket.text)
async def create_ticket_text(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    tg_id = message.from_user.id
    text = message.text.strip()

    # Check if this is a reply to existing ticket
    reply_ticket_id = data.get("reply_ticket_id")
    if reply_ticket_id:
        await execute(
            "INSERT INTO ticket_messages (ticket_id, sender_telegram_id, text, is_admin) "
            "VALUES (?, ?, ?, 0)",
            (reply_ticket_id, tg_id, text))
        await execute(
            "UPDATE support_tickets SET updated_at = datetime('now') WHERE id = ?",
            (reply_ticket_id,))
        await message.answer(
            f"✅ Сообщение отправлено в тикет #{reply_ticket_id}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🎫 Мои тикеты", callback_data="my_tickets")],
            ]))
        return

    # New ticket creation
    subject = data["subject"]
    await execute(
        "INSERT INTO support_tickets (user_telegram_id, subject) VALUES (?, ?)",
        (tg_id, subject))

    ticket = await fetch_one(
        "SELECT id FROM support_tickets WHERE user_telegram_id = ? "
        "ORDER BY created_at DESC LIMIT 1", (tg_id,))

    if ticket:
        await execute(
            "INSERT INTO ticket_messages (ticket_id, sender_telegram_id, text, is_admin) "
            "VALUES (?, ?, ?, 0)",
            (ticket["id"], tg_id, text))

    await message.answer(
        f"✅ Тикет #{ticket['id'] if ticket else '?'} создан!\n\n"
        "Мы ответим вам в ближайшее время.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
        ]))


@router.callback_query(F.data.startswith("reply_ticket_"))
async def reply_ticket_start(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.replace("reply_ticket_", ""))
    await state.update_data(reply_ticket_id=ticket_id)
    await state.set_state(CreateTicket.text)
    await callback.message.edit_text(
        f"Введите сообщение для тикета #{ticket_id}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"my_ticket_{ticket_id}")],
        ]))
    await callback.answer()


# --- Promo codes ---

@router.callback_query(F.data == "enter_promo")
async def enter_promo_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EnterPromo.code)
    await callback.message.edit_text(
        "🎟 <b>Ввод промокода</b>\n\n"
        "Введите промокод:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="my_account")],
        ]), parse_mode="HTML")
    await callback.answer()


@router.message(EnterPromo.code)
async def enter_promo_code(message: Message, state: FSMContext):
    await state.clear()
    code = message.text.strip().upper()
    tg_id = message.from_user.id

    promo = await fetch_one(
        "SELECT * FROM promo_codes WHERE code = ?", (code,))
    if not promo:
        await message.answer(
            "❌ Промокод не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
            ]))
        return

    # Check if valid
    if promo["valid_until"]:
        expired = await fetch_one(
            "SELECT 1 WHERE datetime(?) < datetime('now')",
            (promo["valid_until"],))
        if expired:
            await message.answer(
                "❌ Промокод истёк.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
                ]))
            return

    # Check max uses
    if promo["max_uses"] > 0 and promo["uses_count"] >= promo["max_uses"]:
        await message.answer(
            "❌ Промокод больше недействителен.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
            ]))
        return

    # Check if already used by this user
    already = await fetch_one(
        "SELECT 1 FROM promo_activations "
        "WHERE promo_code_id = ? AND user_telegram_id = ?",
        (promo["id"], tg_id))
    if already:
        await message.answer(
            "❌ Вы уже использовали этот промокод.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
            ]))
        return

    # Activate promo
    await execute(
        "INSERT INTO promo_activations (promo_code_id, user_telegram_id) VALUES (?, ?)",
        (promo["id"], tg_id))
    await execute(
        "UPDATE promo_codes SET uses_count = uses_count + 1 WHERE id = ?",
        (promo["id"],))

    if promo["type"] == "bonus_days":
        bonus_days = int(promo["value"])
        # Check if user has active subscription
        current_sub = await fetch_one(
            "SELECT expires_at FROM subscriptions "
            "WHERE user_telegram_id = ? AND status = 'succeeded' "
            "AND expires_at > datetime('now') "
            "ORDER BY expires_at DESC LIMIT 1",
            (tg_id,))

        if current_sub:
            # Extend existing subscription (use subquery — SQLite doesn't support UPDATE...ORDER BY...LIMIT)
            sub_to_extend = await fetch_one(
                "SELECT id FROM subscriptions "
                "WHERE user_telegram_id = ? AND status = 'succeeded' "
                "AND expires_at > datetime('now') "
                "ORDER BY expires_at DESC LIMIT 1",
                (tg_id,))
            if sub_to_extend:
                await execute(
                    "UPDATE subscriptions SET "
                    "expires_at = datetime(expires_at, '+' || ? || ' days') "
                    "WHERE id = ?",
                    (bonus_days, sub_to_extend["id"]))
        else:
            # Give free access
            await execute(
                "UPDATE users SET status = 'subscription_active', "
                "updated_at = datetime('now') WHERE telegram_id = ?",
                (tg_id,))
            await execute(
                "INSERT INTO subscriptions "
                "(user_telegram_id, plan_id, payment_id, status, amount_rub, "
                "started_at, expires_at) "
                "VALUES (?, 1, 'promo_' || ?, 'succeeded', 0, "
                "datetime('now'), datetime('now', '+' || ? || ' days'))",
                (tg_id, promo["id"], bonus_days))

        await message.answer(
            f"✅ Промокод активирован!\n"
            f"Вы получили <b>{bonus_days} дней</b> доступа.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
            ]), parse_mode="HTML")

    elif promo["type"] == "discount":
        # Store discount for next payment
        discount = int(promo["value"])
        await message.answer(
            f"✅ Промокод активирован!\n"
            f"Скидка <b>{discount}%</b> будет применена при следующей оплате.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Выбрать тариф", callback_data="select_plan")],
                [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
            ]), parse_mode="HTML")
