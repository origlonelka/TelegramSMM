import random
import asyncio
import logging
from pyrogram.errors import (
    FloodWait, PeerFlood,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan,
)
from db.database import execute, fetch_one, fetch_all, execute_returning, delete_account
from services.account_manager import ensure_connected, disconnect

logger = logging.getLogger(__name__)

# Pyrogram 2.0.106+ поддерживает stories через raw API
try:
    from pyrogram.raw.functions.stories import GetPeerStories, ReadStories
    STORIES_AVAILABLE = True
except ImportError:
    STORIES_AVAILABLE = False
    logger.warning("Stories API не доступен в этой версии Pyrogram")


async def run_story_campaign(campaign_id: int):
    """Запускает один цикл просмотра Stories для кампании."""
    if not STORIES_AVAILABLE:
        logger.error(f"Кампания Stories #{campaign_id}: API Stories недоступен")
        return

    camp = await fetch_one(
        "SELECT * FROM campaigns WHERE id = ? AND is_active = 1", (campaign_id,))
    if not camp:
        return

    accounts = await fetch_all("""
        SELECT a.* FROM accounts a
        JOIN campaign_accounts ca ON a.id = ca.account_id
        WHERE ca.campaign_id = ? AND a.status = 'active'
    """, (campaign_id,))

    channels = await fetch_all("""
        SELECT c.* FROM channels c
        JOIN campaign_channels cc ON c.id = cc.channel_id
        WHERE cc.campaign_id = ?
    """, (campaign_id,))

    if not accounts or not channels:
        logger.warning(f"Кампания Stories #{campaign_id}: не хватает данных")
        return

    for channel in channels:
        account = _pick_account(accounts, camp)
        if not account:
            logger.info(f"Кампания Stories #{campaign_id}: все аккаунты достигли лимита")
            break

        await _view_stories(account, channel, camp)

        delay = random.randint(camp["delay_min"], camp["delay_max"])
        await asyncio.sleep(delay)


def _pick_account(accounts: list, camp) -> dict | None:
    """Выбирает аккаунт с наименьшей нагрузкой."""
    available = [
        a for a in accounts
        if a["comments_today"] < camp["daily_limit"]
        and a["comments_hour"] < camp["hourly_limit"]
    ]
    if not available:
        return None
    return min(available, key=lambda a: a["comments_today"])


async def _view_stories(account, channel, camp):
    """Просматривает Stories канала от имени аккаунта."""
    channel_username = channel["username"]
    try:
        client = await ensure_connected(account)

        # Получаем peer для raw API
        peer = await client.resolve_peer(f"@{channel_username}")

        # Получаем Stories канала
        result = await client.invoke(GetPeerStories(peer=peer))

        if not result.stories or not result.stories.stories:
            logger.info(f"Нет Stories у @{channel_username}")
            return

        story_ids = [s.id for s in result.stories.stories]

        # Отмечаем Stories как просмотренные
        await client.invoke(ReadStories(peer=peer, max_id=max(story_ids)))

        # Обновляем счётчики
        await execute(
            "UPDATE accounts SET comments_today = comments_today + 1, "
            "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
            "WHERE id = ?",
            (account["id"],),
        )

        await execute_returning(
            "INSERT INTO logs (account_id, channel_id, mode, status) "
            "VALUES (?, ?, 'stories', 'sent')",
            (account["id"], channel["id"]),
        )

        logger.info(
            f"Stories просмотрены: аккаунт #{account['id']} -> "
            f"@{channel_username} ({len(story_ids)} шт.)"
        )

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв ({type(e).__name__}), удаляю")
        await disconnect(account["id"])
        await delete_account(account["id"])

    except FloodWait as e:
        logger.warning(f"FloodWait: аккаунт #{account['id']}, ждём {e.value} сек")
        await asyncio.sleep(e.value)

    except (PeerFlood,) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен: {e}")
        await execute(
            "UPDATE accounts SET status = 'limited' WHERE id = ?",
            (account["id"],),
        )

    except Exception as e:
        logger.error(f"Ошибка просмотра Stories @{channel_username}: {e}")
        await execute_returning(
            "INSERT INTO logs (account_id, channel_id, mode, status, error) "
            "VALUES (?, ?, 'stories', 'error', ?)",
            (account["id"], channel["id"], str(e)),
        )
