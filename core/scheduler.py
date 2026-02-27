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


async def _reset_hourly_limits():
    """Сбрасывает часовые лимиты аккаунтов."""
    await execute("UPDATE accounts SET comments_hour = 0")
    logger.info("Часовые лимиты сброшены")


async def _reset_daily_limits():
    """Сбрасывает дневные лимиты аккаунтов."""
    await execute("UPDATE accounts SET comments_today = 0, comments_hour = 0")
    logger.info("Дневные лимиты сброшены")


def start_scheduler():
    # Запускать кампании каждые 5 минут
    scheduler.add_job(_run_active_campaigns, "interval", minutes=5, id="campaigns")
    # Сбрасывать часовые лимиты каждый час
    scheduler.add_job(_reset_hourly_limits, "cron", minute=0, id="hourly_reset")
    # Сбрасывать дневные лимиты в полночь
    scheduler.add_job(_reset_daily_limits, "cron", hour=0, minute=0, id="daily_reset")

    scheduler.start()
    logger.info("Планировщик запущен")
