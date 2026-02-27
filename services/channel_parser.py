from pyrogram import Client
from pyrogram.raw.functions.contacts import Search
from core.config import API_ID, API_HASH, SESSIONS_DIR
from db.database import fetch_all

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


async def search_channels(keyword: str, limit: int = 15) -> list[dict]:
    client = await _get_search_client()
    if not client:
        return []

    try:
        result = await client.invoke(Search(q=keyword, limit=limit))
        channels = []
        for chat in result.chats:
            if hasattr(chat, "broadcast") and chat.broadcast:
                channels.append({
                    "username": chat.username or "",
                    "title": chat.title or "",
                })
        return [ch for ch in channels if ch["username"]]
    except Exception:
        return []
