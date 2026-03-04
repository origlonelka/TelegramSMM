"""User access middleware — checks trial/subscription entitlement."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from db.database import fetch_one
from services.user_manager import get_or_create_user, check_entitlement


class UserAccessMiddleware(BaseMiddleware):
    """Checks user entitlement (trial or subscription) before processing.

    Admins bypass paywall. Injects db_user and entitlement into handler data.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        # Admins bypass paywall but still need db_user
        admin = await fetch_one(
            "SELECT role FROM admins WHERE user_id = ? AND is_active = 1",
            (user.id,))
        if admin:
            db_user = await get_or_create_user(
                user.id, user.username, user.first_name)
            data["db_user"] = db_user
            data["is_admin"] = True
            data["admin_role"] = admin["role"]
            return await handler(event, data)

        # Get or create user
        db_user = await get_or_create_user(
            user.id, user.username, user.first_name)
        data["db_user"] = db_user

        # Check entitlement
        entitlement = await check_entitlement(user.id)
        data["entitlement"] = entitlement

        if not entitlement["allowed"]:
            from bot.keyboards.inline import paywall_kb
            status = entitlement["status"]
            if status == "new":
                text = ("Добро пожаловать! У вас ещё нет доступа.\n"
                        "Активируйте бесплатный пробный период на 24 часа "
                        "или выберите тариф:")
            elif status == "blocked":
                if isinstance(event, Message):
                    await event.answer("⛔ Ваш аккаунт заблокирован.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔ Аккаунт заблокирован", show_alert=True)
                return
            else:
                text = "Ваш доступ истёк. Активируйте подписку:"

            if isinstance(event, Message):
                await event.answer(text, reply_markup=paywall_kb(
                    show_trial=status == "new"))
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ истёк", show_alert=True)
            return

        return await handler(event, data)
