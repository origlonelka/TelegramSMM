import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage

from aiohttp import web

from core.config import BOT_TOKEN, WEBHOOK_PORT
from db.database import init_db, close_db
from core.scheduler import start_scheduler
from bot.middlewares.access import UserAccessMiddleware
from core.webhook_server import create_webhook_app, set_bot

from bot.handlers import start, accounts, channels, messages, campaigns, settings, account_setup, presets, proxies, autoreg, payments

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

    # Платежи — без middleware (пользователи без подписки должны иметь доступ)
    dp.include_router(payments.router)

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

    # Запуск webhook-сервера для YooKassa
    set_bot(bot)
    webhook_app = create_webhook_app()
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server started on port {WEBHOOK_PORT}")

    # Запуск бота
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
