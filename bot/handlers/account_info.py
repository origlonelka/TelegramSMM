"""User account info: subscription status, referral system."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.database import fetch_one, fetch_all
from services.user_manager import get_or_create_user, check_entitlement

router = Router()

REFERRAL_BONUS_DAYS = 7


def my_account_kb(has_active_sub: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if has_active_sub:
        buttons.append([InlineKeyboardButton(
            text="💳 Продлить подписку", callback_data="select_plan")])
    else:
        buttons.append([InlineKeyboardButton(
            text="💳 Купить подписку", callback_data="select_plan")])
    buttons.append([InlineKeyboardButton(
        text="👥 Реферальная программа", callback_data="my_referrals")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "my_account")
async def my_account(callback: CallbackQuery):
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
        text += f"Действует до: {sub['expires_at'][:16].replace('T', ' ')}\n"
    elif ent["status"] == "trial_active":
        text += f"Истекает: {ent['expires_at'][:16].replace('T', ' ')}\n"
    text += "\n"

    # Referral section
    from core.config import BOT_URL
    bot_username = BOT_URL.replace("https://t.me/", "") if BOT_URL else ""
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}" if bot_username else ""

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
    from core.config import BOT_URL
    bot_username = BOT_URL.replace("https://t.me/", "") if BOT_URL else ""
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}" if bot_username else ""

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
