"""YooKassa payment management: create payments, process webhooks, manage subscriptions."""
import asyncio
import logging
import uuid
from decimal import Decimal

from yookassa import Configuration, Payment

from core.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, BOT_URL
from db.database import execute, execute_returning, fetch_one, fetch_all

logger = logging.getLogger(__name__)


def _configure_yookassa():
    """Set up YooKassa SDK credentials."""
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY


async def get_active_plans() -> list[dict]:
    """Return all active subscription plans."""
    rows = await fetch_all(
        "SELECT * FROM subscription_plans WHERE is_active = 1 "
        "ORDER BY duration_days ASC"
    )
    return [dict(r) for r in rows]


async def get_plan_by_id(plan_id: int) -> dict | None:
    """Return a single plan by ID."""
    row = await fetch_one(
        "SELECT * FROM subscription_plans WHERE id = ? AND is_active = 1",
        (plan_id,)
    )
    return dict(row) if row else None


async def create_payment(user_telegram_id: int, plan_id: int) -> dict:
    """Create a YooKassa payment and a pending subscription record.

    Returns: {"ok": bool, "confirmation_url": str, "payment_id": str}
             or {"ok": False, "error": str}
    """
    plan = await get_plan_by_id(plan_id)
    if not plan:
        return {"ok": False, "error": "Тариф не найден"}

    payment_uuid = str(uuid.uuid4())

    sub_id = await execute_returning(
        "INSERT INTO subscriptions "
        "(user_telegram_id, plan_id, payment_id, status, amount_rub) "
        "VALUES (?, ?, ?, 'pending', ?)",
        (user_telegram_id, plan_id, payment_uuid, plan["price_rub"])
    )

    _configure_yookassa()
    loop = asyncio.get_event_loop()
    try:
        return_url = BOT_URL or "https://t.me"
        yookassa_payment = await loop.run_in_executor(None, lambda: Payment.create(
            {
                "amount": {
                    "value": str(Decimal(plan["price_rub"])),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": f"Подписка TelegramSMM: {plan['name']}",
                "metadata": {
                    "subscription_id": str(sub_id),
                    "user_telegram_id": str(user_telegram_id),
                    "plan_code": plan["code"],
                }
            },
            idempotency_key=payment_uuid
        ))
    except Exception as e:
        logger.error(f"YooKassa payment creation failed: {e}")
        await execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE id = ?",
            (sub_id,)
        )
        return {"ok": False, "error": f"Ошибка создания платежа: {e}"}

    await execute(
        "UPDATE subscriptions SET yookassa_payment_id = ? WHERE id = ?",
        (yookassa_payment.id, sub_id)
    )

    confirmation_url = yookassa_payment.confirmation.confirmation_url
    return {
        "ok": True,
        "confirmation_url": confirmation_url,
        "payment_id": payment_uuid,
        "subscription_id": sub_id,
    }


async def process_webhook(yookassa_payment_id: str) -> dict:
    """Process a YooKassa payment.succeeded webhook.

    Idempotent: if subscription already activated, returns success without changes.
    """
    existing = await fetch_one(
        "SELECT * FROM subscriptions WHERE yookassa_payment_id = ?",
        (yookassa_payment_id,)
    )
    if existing and existing["status"] == "succeeded":
        return {"ok": True, "already_processed": True,
                "user_telegram_id": existing["user_telegram_id"]}

    if not existing:
        _configure_yookassa()
        loop = asyncio.get_event_loop()
        try:
            yp = await loop.run_in_executor(
                None, lambda: Payment.find_one(yookassa_payment_id))
        except Exception as e:
            logger.error(f"YooKassa find_one failed: {e}")
            return {"ok": False, "error": str(e)}

        if yp.status != "succeeded":
            return {"ok": False, "error": f"Payment status: {yp.status}"}

        meta = yp.metadata or {}
        sub_id = meta.get("subscription_id")
        if sub_id:
            existing = await fetch_one(
                "SELECT * FROM subscriptions WHERE id = ?", (int(sub_id),))

        if not existing:
            logger.warning(
                f"Webhook for unknown payment {yookassa_payment_id}")
            return {"ok": False, "error": "Subscription not found"}

    sub = dict(existing)
    user_tg_id = sub["user_telegram_id"]
    plan = await get_plan_by_id(sub["plan_id"])
    if not plan:
        return {"ok": False, "error": "Plan not found"}

    # Extend if user already has an active subscription
    current_sub = await fetch_one(
        "SELECT expires_at FROM subscriptions "
        "WHERE user_telegram_id = ? AND status = 'succeeded' "
        "AND expires_at > datetime('now') "
        "ORDER BY expires_at DESC LIMIT 1",
        (user_tg_id,)
    )
    if current_sub:
        start_expr = f"datetime('{current_sub['expires_at']}')"
    else:
        start_expr = "datetime('now')"

    duration_days = plan["duration_days"]

    await execute(
        f"UPDATE subscriptions SET "
        f"status = 'succeeded', "
        f"started_at = {start_expr}, "
        f"expires_at = datetime({start_expr}, '+{duration_days} days') "
        f"WHERE id = ?",
        (sub["id"],)
    )

    await execute(
        "UPDATE users SET status = 'subscription_active', "
        "updated_at = datetime('now') WHERE telegram_id = ?",
        (user_tg_id,)
    )

    # Referral bonus: give 7 days to referrer on first payment
    await _give_referral_bonus(user_tg_id)

    return {
        "ok": True,
        "already_processed": False,
        "user_telegram_id": user_tg_id,
        "plan_name": plan["name"],
        "duration_days": duration_days,
    }


async def check_payment_status(payment_uuid: str) -> dict:
    """Manual check of payment status via YooKassa API."""
    sub = await fetch_one(
        "SELECT * FROM subscriptions WHERE payment_id = ?",
        (payment_uuid,)
    )
    if not sub:
        return {"status": "not_found", "paid": False}

    if sub["status"] == "succeeded":
        return {"status": "succeeded", "paid": True}

    if not sub["yookassa_payment_id"]:
        return {"status": "pending", "paid": False}

    _configure_yookassa()
    loop = asyncio.get_event_loop()
    try:
        yp = await loop.run_in_executor(
            None, lambda: Payment.find_one(sub["yookassa_payment_id"]))
    except Exception as e:
        logger.error(f"YooKassa check failed: {e}")
        return {"status": "error", "paid": False}

    if yp.status == "succeeded":
        result = await process_webhook(sub["yookassa_payment_id"])
        return {"status": "succeeded", "paid": True, **result}
    elif yp.status == "canceled":
        await execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE id = ?",
            (sub["id"],)
        )
        return {"status": "cancelled", "paid": False}
    else:
        return {"status": yp.status, "paid": False}


REFERRAL_BONUS_DAYS = 7


async def _give_referral_bonus(user_tg_id: int):
    """Give bonus days to referrer when referred user makes first payment."""
    ref = await fetch_one(
        "SELECT * FROM referrals WHERE referred_telegram_id = ? AND bonus_days = 0",
        (user_tg_id,))
    if not ref:
        return

    referrer_id = ref["referrer_telegram_id"]
    # Mark bonus as given
    await execute(
        "UPDATE referrals SET bonus_days = ? WHERE id = ?",
        (REFERRAL_BONUS_DAYS, ref["id"]))

    # Extend referrer's subscription or create a bonus one
    current_sub = await fetch_one(
        "SELECT expires_at FROM subscriptions "
        "WHERE user_telegram_id = ? AND status = 'succeeded' "
        "AND expires_at > datetime('now') "
        "ORDER BY expires_at DESC LIMIT 1",
        (referrer_id,))

    if current_sub:
        # Extend existing subscription (use subquery — SQLite doesn't support UPDATE...ORDER BY...LIMIT)
        sub_to_extend = await fetch_one(
            "SELECT id FROM subscriptions "
            "WHERE user_telegram_id = ? AND status = 'succeeded' "
            "AND expires_at > datetime('now') "
            "ORDER BY expires_at DESC LIMIT 1",
            (referrer_id,))
        if sub_to_extend:
            await execute(
                "UPDATE subscriptions SET "
                "expires_at = datetime(expires_at, '+' || ? || ' days') "
                "WHERE id = ?",
                (REFERRAL_BONUS_DAYS, sub_to_extend["id"]))
    else:
        # Give free access by updating user status and trial
        referrer = await fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?", (referrer_id,))
        if referrer:
            await execute(
                "UPDATE users SET status = 'subscription_active', "
                "updated_at = datetime('now') WHERE telegram_id = ?",
                (referrer_id,))
            # Create a bonus subscription record
            await execute(
                "INSERT INTO subscriptions "
                "(user_telegram_id, plan_id, payment_id, status, amount_rub, "
                "started_at, expires_at) "
                "VALUES (?, 1, 'referral_bonus_' || ?, 'succeeded', 0, "
                "datetime('now'), datetime('now', '+' || ? || ' days'))",
                (referrer_id, user_tg_id, REFERRAL_BONUS_DAYS))

    logger.info(f"Referral bonus: {REFERRAL_BONUS_DAYS} days to {referrer_id} "
                f"from {user_tg_id}")

    # Notify referrer
    try:
        from core.webhook_server import _bot_instance
        if _bot_instance:
            await _bot_instance.send_message(
                chat_id=referrer_id,
                text=(
                    f"🎉 <b>Реферальный бонус!</b>\n\n"
                    f"Ваш друг оплатил подписку. "
                    f"Вы получили <b>{REFERRAL_BONUS_DAYS} дней</b> доступа!"
                ),
                parse_mode="HTML")
    except Exception:
        pass


async def expire_subscriptions():
    """Mark expired subscriptions. Called by scheduler."""
    expired_users = await fetch_all(
        "SELECT DISTINCT user_telegram_id FROM subscriptions "
        "WHERE status = 'succeeded' AND expires_at <= datetime('now')"
    )
    for row in expired_users:
        tg_id = row["user_telegram_id"]
        still_active = await fetch_one(
            "SELECT 1 FROM subscriptions "
            "WHERE user_telegram_id = ? AND status = 'succeeded' "
            "AND expires_at > datetime('now')",
            (tg_id,)
        )
        if not still_active:
            await execute(
                "UPDATE users SET status = 'expired', "
                "updated_at = datetime('now') WHERE telegram_id = ? "
                "AND status = 'subscription_active'",
                (tg_id,)
            )
            logger.info(f"Subscription expired for user {tg_id}")

    await execute(
        "UPDATE subscriptions SET status = 'expired' "
        "WHERE status = 'succeeded' AND expires_at <= datetime('now')"
    )


async def get_expiring_soon(days: int = 3) -> list[dict]:
    """Get users whose subscription expires within N days."""
    rows = await fetch_all(
        "SELECT s.user_telegram_id, s.expires_at, p.name as plan_name "
        "FROM subscriptions s "
        "JOIN subscription_plans p ON s.plan_id = p.id "
        "WHERE s.status = 'succeeded' "
        "AND s.expires_at > datetime('now') "
        "AND s.expires_at <= datetime('now', ? || ' days') "
        "ORDER BY s.expires_at ASC",
        (str(days),)
    )
    return [dict(r) for r in rows]
