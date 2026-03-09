import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.database import execute, fetch_all
from services.commenter import run_campaign
from services.story_viewer import run_story_campaign
from services.subscriber import run_subscribe_campaign
from services.dm_sender import run_dm_campaign
from services.promo_chatter import run_promo_chat_campaign

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


DISPATCH = {
    "comments": run_campaign,
    "dm": run_dm_campaign,
    "stories": run_story_campaign,
    "subscribe": run_subscribe_campaign,
    "promo_chats": run_promo_chat_campaign,
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
    """Деактивирует истёкшие подписки и триалы."""
    try:
        from services.payment_manager import expire_subscriptions
        await expire_subscriptions()
    except Exception as e:
        logger.error(f"Subscription expiry check failed: {e}")

    # Expire trials
    try:
        await execute(
            "UPDATE users SET status = 'expired', updated_at = datetime('now') "
            "WHERE status = 'trial_active' "
            "AND trial_expires_at IS NOT NULL "
            "AND datetime(trial_expires_at) < datetime('now')")
    except Exception as e:
        logger.error(f"Trial expiry check failed: {e}")


async def _sync_boost_services():
    """Синхронизирует сервисы LikeDrom каждые 2 часа."""
    try:
        from services.boost_manager import sync_services
        count = await sync_services()
        logger.info(f"Синхронизация накрутки: {count} сервисов")
    except Exception as e:
        logger.error(f"Boost services sync failed: {e}")


async def _update_boost_orders():
    """Обновляет статусы заказов накрутки каждые 5 минут."""
    try:
        from services.boost_manager import update_order_statuses
        await update_order_statuses()
    except Exception as e:
        logger.error(f"Boost order status update failed: {e}")


async def _check_likedrom_balance():
    """Проверяет баланс LikeDrom, алерт если < 100₽."""
    try:
        from services import likedrom
        balance = await likedrom.get_balance()
        if balance < 100:
            logger.warning(f"LikeDrom баланс низкий: {balance:.2f} ₽")
            from core.webhook_server import _bot_instance
            if _bot_instance:
                from core.config import SUPERADMIN_IDS
                for admin_id in SUPERADMIN_IDS:
                    try:
                        await _bot_instance.send_message(
                            chat_id=admin_id,
                            text=(
                                f"⚠️ <b>Низкий баланс LikeDrom!</b>\n\n"
                                f"Текущий баланс: <b>{balance:.2f} ₽</b>\n"
                                f"Пополните баланс для продолжения работы накрутки."
                            ),
                            parse_mode="HTML")
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"LikeDrom balance check failed: {e}")


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


async def get_campaign_interval() -> int:
    """Получает интервал запуска кампаний из bot_settings (по умолчанию 5 мин)."""
    row = await fetch_one(
        "SELECT value FROM bot_settings WHERE key = 'campaign_interval_minutes'")
    if row:
        try:
            return max(1, int(row["value"]))
        except (ValueError, TypeError):
            pass
    return 5


async def set_campaign_interval(minutes: int):
    """Устанавливает интервал и перепланирует джоб."""
    minutes = max(1, minutes)
    await execute(
        "INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('campaign_interval_minutes', ?)",
        (str(minutes),))
    # Перепланировать джоб
    scheduler.reschedule_job("campaigns", trigger="interval", minutes=minutes)
    logger.info(f"Интервал кампаний изменён на {minutes} мин")


def start_scheduler(campaign_interval: int = 5):
    # Запускать кампании с настроенным интервалом
    scheduler.add_job(_run_active_campaigns, "interval", minutes=campaign_interval, id="campaigns")
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

    # Накрутка: синхронизация сервисов каждые 2 часа
    scheduler.add_job(_sync_boost_services, "interval", hours=2,
                      id="boost_sync_services")
    # Накрутка: обновление статусов заказов каждые 5 минут
    scheduler.add_job(_update_boost_orders, "interval", minutes=5,
                      id="boost_update_orders")
    # Накрутка: проверка баланса LikeDrom каждые 30 минут
    scheduler.add_job(_check_likedrom_balance, "interval", minutes=30,
                      id="boost_check_balance")

    scheduler.start()
    logger.info("Планировщик запущен")
