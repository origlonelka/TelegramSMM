import random
import asyncio
import logging
from pyrogram.errors import (
    FloodWait, PeerFlood,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked,
)
from db.database import execute, fetch_one, fetch_all, execute_returning, delete_account
from services.account_manager import ensure_connected, disconnect

logger = logging.getLogger(__name__)

# Безопасный лимит лайков на stories в день на аккаунт
DAILY_LIKE_LIMIT = 30

# Pyrogram 2.0.106+ поддерживает stories через raw API
try:
    from pyrogram.raw.functions.stories import GetPeerStories, ReadStories, SendReaction
    from pyrogram.raw.types import ReactionEmoji
    STORIES_AVAILABLE = True
    LIKES_AVAILABLE = True
except ImportError:
    STORIES_AVAILABLE = False
    LIKES_AVAILABLE = False
    logger.warning("Stories API не доступен в этой версии Pyrogram")

# Эмодзи для лайков на stories (рандомно выбираем)
LIKE_REACTIONS = ["❤", "🔥", "👍", "😍"]


async def run_story_campaign(campaign_id: int):
    """Запускает один цикл просмотра Stories для кампании.

    Каждый аккаунт работает параллельно со своим КД.
    """
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

    # Запускаем параллельного воркера на каждый аккаунт
    tasks = []
    for account in accounts:
        if account["comments_today"] >= camp["daily_limit"]:
            continue
        if account["comments_hour"] >= camp["hourly_limit"]:
            continue
        tasks.append(_account_worker(account, channels, camp))

    if not tasks:
        logger.info(f"Кампания Stories #{campaign_id}: все аккаунты достигли лимита")
        return

    logger.info(f"Кампания Stories #{campaign_id}: запуск {len(tasks)} аккаунтов параллельно")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.error(f"Кампания Stories #{campaign_id}: воркер завершился с ошибкой: {result}")


async def _account_worker(account, channels, camp):
    """Воркер одного аккаунта — проходит каналы со своим КД."""
    shuffled = list(channels)
    random.shuffle(shuffled)

    for channel in shuffled:
        # Перепроверяем лимиты из БД
        acc_fresh = await fetch_one("SELECT * FROM accounts WHERE id = ?", (account["id"],))
        if not acc_fresh or acc_fresh["status"] != "active":
            break
        if acc_fresh["comments_today"] >= camp["daily_limit"]:
            break
        if acc_fresh["comments_hour"] >= camp["hourly_limit"]:
            break

        await _view_stories(account, channel, camp)

        delay = random.randint(
            max(camp["delay_min"], 30),
            max(camp["delay_max"], 60),
        )
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info(f"Кампания Stories #{camp['id']}: аккаунт #{account['id']} прерван во время задержки")
            return


async def _get_likes_today(account_id: int) -> int:
    """Считает количество лайков аккаунта за сегодня."""
    row = await fetch_one(
        "SELECT COUNT(*) as cnt FROM logs WHERE account_id = ? "
        "AND mode = 'stories_like' AND status = 'sent' "
        "AND date(sent_at) = date('now')",
        (account_id,),
    )
    return row["cnt"] if row else 0


async def _try_like_story(client, peer, story_id: int, account, channel, camp=None) -> bool:
    """Пытается лайкнуть story. Возвращает True при успехе."""
    if not LIKES_AVAILABLE:
        return False

    # Проверяем дневной лимит лайков
    likes_today = await _get_likes_today(account["id"])
    if likes_today >= DAILY_LIKE_LIMIT:
        logger.info(
            f"Аккаунт #{account['id']}: лимит лайков на сегодня ({DAILY_LIKE_LIMIT}) исчерпан"
        )
        return False

    # Проверяем, не лайкали ли уже эту story
    already_liked = await fetch_one(
        "SELECT 1 FROM logs WHERE account_id = ? AND channel_id = ? "
        "AND mode = 'stories_like' AND post_id = ? AND status = 'sent'",
        (account["id"], channel["id"], story_id),
    )
    if already_liked:
        logger.debug(f"Story {story_id} уже лайкнута аккаунтом #{account['id']}")
        return False

    try:
        reaction = ReactionEmoji(emoticon=random.choice(LIKE_REACTIONS))
        await client.invoke(SendReaction(
            peer=peer,
            story_id=story_id,
            reaction=reaction,
        ))

        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, post_id, mode, status) "
            "VALUES (?, ?, ?, ?, 'stories_like', 'sent')",
            (camp["id"] if camp else None, account["id"], channel["id"], story_id),
        )

        logger.info(
            f"Story {story_id} лайкнута ({reaction.emoticon}): "
            f"аккаунт #{account['id']} -> @{channel['username']}"
        )
        return True

    except FloodWait as e:
        logger.warning(
            f"FloodWait при лайке story: аккаунт #{account['id']}, {e.value} сек — пропускаю лайк"
        )
        return False

    except Exception as e:
        logger.debug(f"Не удалось лайкнуть story {story_id}: {type(e).__name__}: {e}")
        return False


async def _view_stories(account, channel, camp):
    """Просматривает Stories канала и лайкает (если лимит не исчерпан)."""
    channel_username = channel["username"]

    # Проверяем, не смотрели ли уже Stories этого канала этим аккаунтом сегодня
    already_viewed = await fetch_one(
        "SELECT 1 FROM logs WHERE account_id = ? AND channel_id = ? "
        "AND mode = 'stories' AND status = 'sent' "
        "AND date(sent_at) = date('now')",
        (account["id"], channel["id"]),
    )
    if already_viewed:
        logger.info(
            f"Stories @{channel_username} уже просмотрены аккаунтом #{account['id']} сегодня, пропускаю"
        )
        return

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

        # Пробуем лайкнуть случайную story
        liked = False
        random.shuffle(story_ids)
        for sid in story_ids:
            liked = await _try_like_story(client, peer, sid, account, channel, camp)
            if liked:
                break
            # Небольшая пауза между попытками лайка
            await asyncio.sleep(random.randint(2, 5))

        # Обновляем счётчики
        await execute(
            "UPDATE accounts SET comments_today = comments_today + 1, "
            "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
            "WHERE id = ?",
            (account["id"],),
        )

        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, mode, status) "
            "VALUES (?, ?, ?, 'stories', 'sent')",
            (camp["id"], account["id"], channel["id"]),
        )

        like_info = " + лайк ❤" if liked else ""
        logger.info(
            f"Stories просмотрены{like_info}: аккаунт #{account['id']} -> "
            f"@{channel_username} ({len(story_ids)} шт.)"
        )

    except asyncio.CancelledError:
        logger.info(f"Просмотр Stories прерван (shutdown), аккаунт #{account['id']} -> @{channel_username}")
        raise

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв ({type(e).__name__}), удаляю")
        await disconnect(account["id"])
        await delete_account(account["id"])

    except FloodWait as e:
        logger.warning(f"FloodWait: аккаунт #{account['id']}, ждём {e.value} сек")
        try:
            await asyncio.sleep(e.value)
        except asyncio.CancelledError:
            logger.info(f"FloodWait sleep прерван (shutdown), аккаунт #{account['id']}")
            return

    except (PeerFlood,) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен: {e}")
        await execute(
            "UPDATE accounts SET status = 'limited' WHERE id = ?",
            (account["id"],),
        )

    except Exception as e:
        logger.error(f"Ошибка просмотра Stories @{channel_username}: {e}")
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, mode, status, error) "
            "VALUES (?, ?, ?, 'stories', 'error', ?)",
            (camp["id"], account["id"], channel["id"], str(e)),
        )
