import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.database import execute, fetch_all
from services.commenter import run_campaign
from services.story_viewer import run_story_campaign
from services.subscriber import run_subscribe_campaign
from services.dm_sender import run_dm_campaign

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


DISPATCH = {
    "comments": run_campaign,
    "dm": run_dm_campaign,
    "stories": run_story_campaign,
    "subscribe": run_subscribe_campaign,
}


async def _run_active_campaigns():
    """Запускает все активные кампании параллельно."""
    try:
        campaigns = await fetch_all(
            "SELECT id, name, mode FROM campaigns WHERE is_active = 1")
        if not campaigns:
            return

        tasks = []
        for camp in campaigns:
            modes = (camp["mode"] or "comments").split(",")
            logger.info(f"Запуск кампании: {camp['name']} (#{camp['id']}, режимы={','.join(modes)})")
            for mode in modes:
                handler = DISPATCH.get(mode)
                if not handler:
                    logger.warning(f"Неизвестный режим '{mode}' у кампании #{camp['id']}")
                    continue
                tasks.append(_run_single(handler, camp["id"], camp["name"], mode))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    except asyncio.CancelledError:
        logger.info("Запуск кампаний прерван (shutdown)")
        return


async def _run_single(handler, camp_id: int, camp_name: str, mode: str):
    """Обёртка для запуска одной кампании с логированием ошибок."""
    try:
        await handler(camp_id)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Ошибка кампании #{camp_id} ({camp_name}) режим={mode}: {e}")


async def _reset_hourly_limits():
    """Сбрасывает часовые лимиты аккаунтов."""
    await execute("UPDATE accounts SET comments_hour = 0")
    logger.info("Часовые лимиты сброшены")


async def _reset_daily_limits():
    """Сбрасывает дневные лимиты аккаунтов."""
    await execute("UPDATE accounts SET comments_today = 0, comments_hour = 0")
    logger.info("Дневные лимиты сброшены")


async def _check_subscription_expiry():
    """Деактивирует истёкшие подписки."""
    try:
        from services.payment_manager import expire_subscriptions
        await expire_subscriptions()
    except Exception as e:
        logger.error(f"Subscription expiry check failed: {e}")


async def _send_expiry_notifications():
    """Уведомляет пользователей об истекающих подписках (за 3 дня)."""
    try:
        from services.payment_manager import get_expiring_soon
        expiring = await get_expiring_soon(days=3)
        if not expiring:
            return

        from core.webhook_server import _bot_instance
        if not _bot_instance:
            return

        from bot.keyboards.inline import subscription_info_kb
        for sub in expiring:
            try:
                await _bot_instance.send_message(
                    chat_id=sub["user_telegram_id"],
                    text=(
                        f"⏳ <b>Подписка скоро истечёт</b>\n\n"
                        f"Ваш тариф «{sub['plan_name']}» действует до "
                        f"{sub['expires_at'][:16]}.\n\n"
                        f"Продлите подписку, чтобы не потерять доступ!"
                    ),
                    reply_markup=subscription_info_kb(),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(
                    f"Failed to notify user {sub['user_telegram_id']}: {e}")
    except Exception as e:
        logger.error(f"Expiry notification failed: {e}")


def start_scheduler():
    # Запускать кампании каждые 5 минут
    scheduler.add_job(_run_active_campaigns, "interval", minutes=5, id="campaigns")
    # Сбрасывать часовые лимиты каждый час
    scheduler.add_job(_reset_hourly_limits, "cron", minute=0, id="hourly_reset")
    # Сбрасывать дневные лимиты в полночь
    scheduler.add_job(_reset_daily_limits, "cron", hour=0, minute=0, id="daily_reset")
    # Проверять истёкшие подписки каждый час (в :30)
    scheduler.add_job(_check_subscription_expiry, "cron", minute=30,
                      id="subscription_expiry")
    # Уведомления об истечении подписки — ежедневно в 10:00
    scheduler.add_job(_send_expiry_notifications, "cron", hour=10, minute=0,
                      id="expiry_notifications")

    scheduler.start()
    logger.info("Планировщик запущен")
