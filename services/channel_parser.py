import logging
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.raw.functions.contacts import Search
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
        logger.warning("Нет активных аккаунтов для поиска")
        return None

    from services.account_manager import ensure_connected
    _search_client = await ensure_connected(accounts[0])
    return _search_client


async def search_channels(keyword: str, limit: int = 30) -> list[dict]:
    """Ищет каналы через contacts.Search + search_global + прямой get_chat."""
    client = await _get_search_client()
    if not client:
        return []

    found: dict[str, dict] = {}

    # 1. contacts.Search — поиск по названию и username публичных каналов
    try:
        result = await client.invoke(Search(q=keyword, limit=limit))
        for chat in result.chats:
            if getattr(chat, "broadcast", False) and getattr(chat, "username", None):
                found[chat.username.lower()] = {
                    "username": chat.username,
                    "title": getattr(chat, "title", "") or "",
                }
        logger.info(f"contacts.Search '{keyword}': найдено {len(found)} каналов")
    except Exception as e:
        logger.warning(f"contacts.Search error: {e}", exc_info=True)

    # 2. search_global — поиск по сообщениям (дополняет результаты)
    try:
        async for msg in client.search_global(keyword, limit=limit):
            chat = msg.chat
            if chat.type == ChatType.CHANNEL and chat.username:
                key = chat.username.lower()
                if key not in found:
                    found[key] = {
                        "username": chat.username,
                        "title": chat.title or "",
                    }
    except Exception as e:
        logger.warning(f"search_global error: {e}")

    # 3. Прямой поиск по username (если запрос похож на юзернейм)
    clean = keyword.strip().lstrip("@")
    if clean.replace("_", "").isalnum() and len(clean) >= 3:
        try:
            chat = await client.get_chat(clean)
            if chat.type == ChatType.CHANNEL and chat.username:
                key = chat.username.lower()
                if key not in found:
                    found[key] = {
                        "username": chat.username,
                        "title": chat.title or "",
                    }
        except Exception:
            pass

    logger.info(f"Итого по запросу '{keyword}': {len(found)} каналов")
    return list(found.values())
