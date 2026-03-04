"""Lightweight aiohttp server for YooKassa webhook notifications."""
import json
import logging

from aiohttp import web

from core.config import WEBHOOK_SECRET
from services.payment_manager import process_webhook

logger = logging.getLogger(__name__)

_bot_instance = None


def set_bot(bot):
    """Store bot instance for sending notifications to users after payment."""
    global _bot_instance
    _bot_instance = bot


async def handle_webhook(request: web.Request) -> web.Response:
    """Handle YooKassa payment.succeeded webhook."""
    if WEBHOOK_SECRET:
        secret = request.match_info.get("secret", "")
        if secret != WEBHOOK_SECRET:
            logger.warning("Webhook rejected: invalid secret")
            return web.Response(status=403)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.Response(status=400, text="Invalid JSON")

    event_type = body.get("event")
    if event_type != "payment.succeeded":
        logger.debug(f"Ignoring webhook event: {event_type}")
        return web.Response(status=200, text="OK")

    payment_obj = body.get("object", {})
    yookassa_payment_id = payment_obj.get("id")
    if not yookassa_payment_id:
        return web.Response(status=400, text="Missing payment ID")

    logger.info(f"Processing webhook for payment {yookassa_payment_id}")
    result = await process_webhook(yookassa_payment_id)

    if result.get("ok") and not result.get("already_processed"):
        user_tg_id = result.get("user_telegram_id")
        if _bot_instance and user_tg_id:
            try:
                from bot.keyboards.inline import main_menu_kb
                plan_name = result.get("plan_name", "")
                await _bot_instance.send_message(
                    chat_id=user_tg_id,
                    text=(
                        f"✅ <b>Оплата прошла успешно!</b>\n\n"
                        f"Тариф: {plan_name}\n"
                        f"Спасибо за подписку! Выберите раздел:"
                    ),
                    reply_markup=main_menu_kb(),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_tg_id}: {e}")

    if result.get("ok"):
        return web.Response(status=200, text="OK")
    else:
        logger.error(f"Webhook processing failed: {result}")
        return web.Response(status=200, text="OK")


def create_webhook_app() -> web.Application:
    """Create aiohttp Application with webhook route."""
    app = web.Application()
    if WEBHOOK_SECRET:
        app.router.add_post("/webhook/{secret}", handle_webhook)
    else:
        app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    return app
