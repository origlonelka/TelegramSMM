import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.database import execute, fetch_all
from services.commenter import run_campaign

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_active_campaigns():
    """Запускает все активные кампании."""
    campaigns = await fetch_all("SELECT id, name FROM campaigns WHERE is_active = 1")
    for camp in campaigns:
        logger.info(f"Запуск кампании: {camp['name']} (#{camp['id']})")
        try:
            await run_campaign(camp["id"])
        except Exception as e:
            logger.error(f"Ошибка кампании #{camp['id']}: {e}")


async def _wake_up_cooldown_accounts():
    """Возвращает аккаунты из отлёжки, если время кулдауна истекло."""
    await execute(
        "UPDATE accounts SET status = 'active', cooldown_until = NULL "
        "WHERE status = 'cooldown' AND cooldown_until IS NOT NULL AND cooldown_until <= datetime('now')"
    )
    # Также чистим cooldown_until у active аккаунтов, у которых время прошло
    await execute(
        "UPDATE accounts SET cooldown_until = NULL "
        "WHERE status = 'active' AND cooldown_until IS NOT NULL AND cooldown_until <= datetime('now')"
    )


async def _reset_hourly_limits():
    """Сбрасывает часовые лимиты аккаунтов."""
    await execute("UPDATE accounts SET comments_hour = 0")
    logger.info("Часовые лимиты сброшены")


async def _reset_daily_limits():
    """Сбрасывает дневные лимиты аккаунтов."""
    await execute("UPDATE accounts SET comments_today = 0, comments_hour = 0")
    logger.info("Дневные лимиты сброшены")


def start_scheduler():
    # Возвращать аккаунты из отлёжки каждые 5 минут
    scheduler.add_job(_wake_up_cooldown_accounts, "interval", minutes=5, id="wake_cooldown")
    # Запускать кампании каждые 5 минут
    scheduler.add_job(_run_active_campaigns, "interval", minutes=5, id="campaigns")
    # Сбрасывать часовые лимиты каждый час
    scheduler.add_job(_reset_hourly_limits, "cron", minute=0, id="hourly_reset")
    # Сбрасывать дневные лимиты в полночь
    scheduler.add_job(_reset_daily_limits, "cron", hour=0, minute=0, id="daily_reset")

    scheduler.start()
    logger.info("Планировщик запущен")
