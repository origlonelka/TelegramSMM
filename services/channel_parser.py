import logging
import random
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.raw.functions.contacts import Search
from db.database import fetch_all, fetch_one

logger = logging.getLogger(__name__)

_search_client: Client | None = None
_last_account_id: int | None = None


async def _get_search_client() -> Client | None:
    """Использует случайный активный аккаунт для поиска каналов (с ротацией)."""
    global _search_client, _last_account_id

    if _search_client and _search_client.is_connected:
        return _search_client

    accounts = await fetch_all("SELECT * FROM accounts WHERE status = 'active'")
    if not accounts:
        logger.warning("Нет активных аккаунтов для поиска")
        return None

    # Ротация: исключаем последний использованный аккаунт если есть другие
    candidates = [a for a in accounts if a["id"] != _last_account_id] or accounts
    account = random.choice(candidates)
    _last_account_id = account["id"]

    from services.account_manager import ensure_connected
    try:
        _search_client = await ensure_connected(account)
    except Exception as e:
        logger.warning(f"Не удалось подключить аккаунт #{account['id']}: {e}")
        # Попробуем другой аккаунт
        for acc in accounts:
            if acc["id"] == account["id"]:
                continue
            try:
                _search_client = await ensure_connected(acc)
                _last_account_id = acc["id"]
                break
            except Exception:
                continue
        else:
            return None
    return _search_client


def _format_subscribers(count: int) -> str:
    """Форматирует число подписчиков в читаемый вид."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


async def _enrich_channel(client: Client, username: str, title: str) -> dict:
    """Получает дополнительную информацию о канале: подписчики, комментарии."""
    result = {
        "username": username,
        "title": title,
        "members_count": 0,
        "members_formatted": "?",
        "has_comments": False,
    }
    try:
        full_chat = await client.get_chat(username)
        result["members_count"] = full_chat.members_count or 0
        result["members_formatted"] = _format_subscribers(result["members_count"])
        # linked_chat указывает на группу обсуждения (комментарии)
        result["has_comments"] = full_chat.linked_chat is not None
    except Exception as e:
        logger.debug(f"Не удалось обогатить канал @{username}: {e}")
    return result


async def search_channels(keyword: str, limit: int = 50) -> list[dict]:
    """Ищет каналы через contacts.Search + search_global + прямой get_chat.

    Возвращает список с доп. информацией: подписчики, комментарии, флаг 'уже добавлен'.
    """
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

    # 4. Обогащаем данные: подписчики + комментарии
    enriched = []
    for ch_data in found.values():
        info = await _enrich_channel(client, ch_data["username"], ch_data["title"])
        enriched.append(info)

    # 5. Помечаем уже добавленные каналы
    existing = await fetch_all("SELECT username FROM channels")
    existing_set = {row["username"].lower() for row in existing}
    for ch in enriched:
        ch["already_added"] = ch["username"].lower() in existing_set

    # 6. Сортировка: сначала с комментариями, потом по подписчикам (убывание)
    enriched.sort(key=lambda x: (not x["has_comments"], -x["members_count"]))

    logger.info(f"Итого по запросу '{keyword}': {len(enriched)} каналов")
    return enriched
