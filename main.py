import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import BOT_TOKEN
from db.database import init_db, close_db
from core.scheduler import start_scheduler
from bot.middlewares.access import UserAccessMiddleware

from bot.handlers import start, accounts, channels, messages, campaigns, settings, account_setup, presets, proxies, autoreg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    # Инициализация БД
    await init_db()
    logger.info("База данных инициализирована")

    # Создание бота
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # /start — без middleware (обрабатывает trial/paywall сам)
    dp.include_router(start.router)

    # Рабочие роутеры — с UserAccessMiddleware (проверяет trial/подписку)
    work_router = Router(name="work")
    work_router.message.middleware(UserAccessMiddleware())
    work_router.callback_query.middleware(UserAccessMiddleware())
    work_router.include_router(accounts.router)
    work_router.include_router(channels.router)
    work_router.include_router(messages.router)
    work_router.include_router(campaigns.router)
    work_router.include_router(account_setup.router)
    work_router.include_router(presets.router)
    work_router.include_router(proxies.router)
    work_router.include_router(autoreg.router)
    work_router.include_router(settings.router)
    dp.include_router(work_router)

    # Запуск планировщика
    start_scheduler()
    logger.info("Планировщик запущен")

    # Запуск бота
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
