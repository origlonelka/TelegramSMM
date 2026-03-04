import asyncio
import logging
from typing import Any, Awaitable, Callable
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import BOT_TOKEN, ADMIN_IDS, ADMIN_USERNAMES
from db.database import init_db, close_db
from core.scheduler import start_scheduler

from bot.handlers import start, accounts, channels, messages, campaigns, settings, account_setup, presets, proxies, autoreg


class AccessMiddleware(BaseMiddleware):
    """Пропускает только пользователей из ADMIN_IDS."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user and user.id not in ADMIN_IDS:
            username = (user.username or "").lower()
            if not username or username not in ADMIN_USERNAMES:
                if isinstance(event, Message):
                    await event.answer("⛔ У вас нет доступа к этому боту.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔ Нет доступа", show_alert=True)
                return
        return await handler(event, data)

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

    # Middleware проверки доступа
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(accounts.router)
    dp.include_router(channels.router)
    dp.include_router(messages.router)
    dp.include_router(campaigns.router)
    dp.include_router(account_setup.router)
    dp.include_router(presets.router)
    dp.include_router(proxies.router)
    dp.include_router(autoreg.router)
    dp.include_router(settings.router)

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
