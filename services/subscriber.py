import random
import asyncio
import logging
from pyrogram.errors import (
    FloodWait, PeerFlood,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked,
    UserAlreadyParticipant, ChannelPrivate, InviteRequestSent,
)
from db.database import execute, fetch_one, fetch_all, execute_returning, delete_account
from services.account_manager import ensure_connected, disconnect

logger = logging.getLogger(__name__)


async def run_subscribe_campaign(campaign_id: int):
    """Запускает один цикл подписки + просмотра для кампании.

    Каждый аккаунт работает параллельно со своим КД.
    """
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
        logger.warning(f"Кампания Subscribe #{campaign_id}: не хватает данных")
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
        logger.info(f"Кампания Subscribe #{campaign_id}: все аккаунты достигли лимита")
        return

    logger.info(f"Кампания Subscribe #{campaign_id}: запуск {len(tasks)} аккаунтов параллельно")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.error(f"Кампания Subscribe #{campaign_id}: воркер завершился с ошибкой: {result}")


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

        await _subscribe_and_view(account, channel, camp)

        delay = random.randint(
            max(camp["delay_min"], 60),
            max(camp["delay_max"], 120),
        )
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info(f"Кампания Subscribe #{camp['id']}: аккаунт #{account['id']} прерван во время задержки")
            return


async def _subscribe_and_view(account, channel, camp):
    """Подписывается на канал и просматривает последние посты."""
    channel_username = channel["username"]

    # Проверяем, не подписывались ли уже на этот канал этим аккаунтом
    already_done = await fetch_one(
        "SELECT 1 FROM logs WHERE account_id = ? AND channel_id = ? "
        "AND mode = 'subscribe' AND status = 'sent'",
        (account["id"], channel["id"]),
    )
    if already_done:
        logger.info(
            f"Аккаунт #{account['id']} уже подписан на @{channel_username} (по логам), пропускаю"
        )
        return

    try:
        client = await ensure_connected(account)

        # 1. Подписываемся на канал
        try:
            await client.join_chat(f"@{channel_username}")
            logger.info(f"Аккаунт #{account['id']} подписался на @{channel_username}")
        except UserAlreadyParticipant:
            logger.info(f"Аккаунт #{account['id']} уже подписан на @{channel_username}")
        except InviteRequestSent:
            logger.info(f"Аккаунт #{account['id']} отправил заявку в @{channel_username}")
        except ChannelPrivate:
            logger.warning(f"@{channel_username} — закрытый канал, пропускаю")
            return

        # 2. Просматриваем последние посты (имитация чтения)
        view_count = random.randint(3, 10)
        viewed = 0
        async for post in client.get_chat_history(f"@{channel_username}", limit=view_count):
            viewed += 1

        logger.info(
            f"Просмотрено {viewed} постов: аккаунт #{account['id']} -> @{channel_username}"
        )

        # Обновляем счётчики
        await execute(
            "UPDATE accounts SET comments_today = comments_today + 1, "
            "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
            "WHERE id = ?",
            (account["id"],),
        )

        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, mode, status) "
            "VALUES (?, ?, ?, 'subscribe', 'sent')",
            (camp["id"], account["id"], channel["id"]),
        )

    except asyncio.CancelledError:
        logger.info(f"Подписка @{channel_username} прервана (shutdown), аккаунт #{account['id']}")
        raise

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв ({type(e).__name__}), удаляю")
        await disconnect(account["id"])
        await delete_account(account["id"])
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, mode, status, error) "
            "VALUES (?, ?, ?, 'subscribe', 'error', ?)",
            (camp["id"], account["id"], channel["id"], f"DELETED: {e}"),
        )

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
        logger.error(f"Ошибка подписки @{channel_username}: {e}")
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, mode, status, error) "
            "VALUES (?, ?, ?, 'subscribe', 'error', ?)",
            (camp["id"], account["id"], channel["id"], str(e)),
        )
