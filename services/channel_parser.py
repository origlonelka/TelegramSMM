import logging
from pyrogram import Client
from pyrogram.enums import ChatType
from db.database import fetch_all

logger = logging.getLogger(__name__)

_search_client: Client | None = None


async def _get_search_client() -> Client | None:
    """Использует первый активный аккаунт для поиска каналов."""
    global _search_client
    if _search_client and _search_client.is_connected:
        return _search_client

    accounts = await fetch_all("SELECT * FROM accounts WHERE status = 'active' LIMIT 1")
    if not accounts:
        return None

    from services.account_manager import ensure_connected
    _search_client = await ensure_connected(accounts[0])
    return _search_client


async def search_channels(keyword: str, limit: int = 20) -> list[dict]:
    """Ищет каналы через search_global + прямой поиск по username."""
    client = await _get_search_client()
    if not client:
        return []

    found: dict[str, dict] = {}

    # 1. Глобальный поиск по ключевому слову
    try:
        async for dialog in client.search_global(keyword, limit=limit):
            chat = dialog.chat
            if chat.type == ChatType.CHANNEL and chat.username:
                found[chat.username.lower()] = {
                    "username": chat.username,
                    "title": chat.title or "",
                }
    except Exception as e:
        logger.warning(f"search_global error: {e}")

    # 2. Прямой поиск по username (если запрос похож на юзернейм)
    clean = keyword.strip().lstrip("@")
    if clean.replace("_", "").isalnum() and len(clean) >= 3:
        try:
            chat = await client.get_chat(clean)
            if chat.type == ChatType.CHANNEL and chat.username:
                found[chat.username.lower()] = {
                    "username": chat.username,
                    "title": chat.title or "",
                }
        except Exception:
            pass

    return list(found.values())
