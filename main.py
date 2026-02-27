import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import BOT_TOKEN
from db.database import init_db
from core.scheduler import start_scheduler

from bot.handlers import start, accounts, channels, messages, campaigns, settings

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

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(accounts.router)
    dp.include_router(channels.router)
    dp.include_router(messages.router)
    dp.include_router(campaigns.router)
    dp.include_router(settings.router)

    # Запуск планировщика
    start_scheduler()
    logger.info("Планировщик запущен")

    # Запуск бота
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
