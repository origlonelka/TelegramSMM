"""Admin middleware — checks admins table with role hierarchy."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from core.config import SUPERADMIN_IDS
from db.database import fetch_one

ROLE_HIERARCHY = {
    "superadmin": 4,
    "admin": 3,
    "finance": 2,
    "support": 1,
}


class AdminMiddleware(BaseMiddleware):
    """Checks that user is in admins table with appropriate role level."""

    def __init__(self, min_role: str = "support"):
        self.min_level = ROLE_HIERARCHY.get(min_role, 0)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user:
            return

        # SUPERADMIN_IDS always have max level
        if user.id in SUPERADMIN_IDS:
            data["admin"] = {"user_id": user.id, "role": "superadmin"}
            return await handler(event, data)

        admin = await fetch_one(
            "SELECT * FROM admins WHERE user_id = ? AND is_active = 1",
            (user.id,))
        if not admin:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа к админ-панели", show_alert=True)
            return

        level = ROLE_HIERARCHY.get(admin["role"], 0)
        if level < self.min_level:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Недостаточно прав", show_alert=True)
            return

        data["admin"] = dict(admin)
        return await handler(event, data)
