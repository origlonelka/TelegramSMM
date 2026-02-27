import random
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram.errors import FloodWait, PeerFlood, UserBannedInChannel, AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan
from db.database import execute, fetch_one, fetch_all, execute_returning, delete_account
from services.account_manager import ensure_connected, disconnect
from services.spintax import spin

logger = logging.getLogger(__name__)


async def run_campaign(campaign_id: int):
    """Запускает один цикл рассылки для кампании."""
    camp = await fetch_one("SELECT * FROM campaigns WHERE id = ? AND is_active = 1", (campaign_id,))
    if not camp:
        return

    # Получаем привязанные сущности
    channels = await fetch_all("""
        SELECT c.* FROM channels c
        JOIN campaign_channels cc ON c.id = cc.channel_id
        WHERE cc.campaign_id = ? AND c.has_comments = 1
    """, (campaign_id,))

    messages = await fetch_all("""
        SELECT m.* FROM messages m
        JOIN campaign_messages cm ON m.id = cm.message_id
        WHERE cm.campaign_id = ? AND m.is_active = 1
    """, (campaign_id,))

    if not channels or not messages:
        logger.warning(f"Кампания #{campaign_id}: не хватает данных (каналы/сообщения)")
        return

    for channel in channels:
        # Выбираем аккаунт с наименьшей нагрузкой (свежие данные из БД)
        account = await _pick_account(campaign_id, camp)
        if not account:
            logger.info(f"Кампания #{campaign_id}: все аккаунты в отлёжке или достигли лимита")
            break

        # Выбираем случайное сообщение
        message = random.choice(messages)

        # Отправляем комментарий
        await _send_comment(account, channel, message, camp)

        # Случайная задержка
        delay = random.randint(camp["delay_min"], camp["delay_max"])
        await asyncio.sleep(delay)


async def _pick_account(campaign_id: int, camp) -> dict | None:
    """Выбирает аккаунт с наименьшей нагрузкой, который не в кулдауне и не достиг лимитов."""
    accounts = await fetch_all("""
        SELECT a.* FROM accounts a
        JOIN campaign_accounts ca ON a.id = ca.account_id
        WHERE ca.campaign_id = ? AND a.status = 'active'
          AND (a.cooldown_until IS NULL OR a.cooldown_until <= datetime('now'))
          AND a.comments_today < ?
          AND a.comments_hour < ?
        ORDER BY a.comments_today ASC
        LIMIT 1
    """, (campaign_id, camp["daily_limit"], camp["hourly_limit"]))

    return accounts[0] if accounts else None


async def _send_comment(account, channel, message, camp):
    """Отправляет комментарий в канал от имени аккаунта."""
    try:
        client = await ensure_connected(account)

        # Получаем последний пост канала
        async for post in client.get_chat_history(f"@{channel['username']}", limit=1):
            if not post.id:
                break

            # Обрабатываем spintax и отправляем комментарий
            comment_text = spin(message["text"])
            await client.send_message(
                chat_id=f"@{channel['username']}",
                text=comment_text,
                reply_to_message_id=post.id,
            )

            # Обновляем счётчики
            await execute(
                "UPDATE accounts SET comments_today = comments_today + 1, "
                "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
                "WHERE id = ?",
                (account["id"],),
            )

            # Проверяем лимиты — если достигнут, ставим в отлёжку
            updated = await fetch_one("SELECT comments_today, comments_hour FROM accounts WHERE id = ?", (account["id"],))
            if updated and updated["comments_today"] >= camp["daily_limit"]:
                # Отлёжка до полуночи
                await execute(
                    "UPDATE accounts SET cooldown_until = date('now', '+1 day') WHERE id = ?",
                    (account["id"],),
                )
                logger.info(f"Аккаунт #{account['id']}: достигнут дневной лимит, отлёжка до полуночи")
            elif updated and updated["comments_hour"] >= camp["hourly_limit"]:
                # Отлёжка на 1 час
                await execute(
                    "UPDATE accounts SET cooldown_until = datetime('now', '+1 hour') WHERE id = ?",
                    (account["id"],),
                )
                logger.info(f"Аккаунт #{account['id']}: достигнут часовой лимит, отлёжка на 1 час")

            # Логируем
            await execute_returning(
                "INSERT INTO logs (account_id, channel_id, message_id, post_id, status) "
                "VALUES (?, ?, ?, ?, 'sent')",
                (account["id"], channel["id"], message["id"], post.id),
            )

            logger.info(
                f"Комментарий отправлен: аккаунт #{account['id']} -> "
                f"@{channel['username']} (пост {post.id})"
            )
            break

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв ({type(e).__name__}), удаляю")
        await disconnect(account["id"])
        await delete_account(account["id"])
        await execute_returning(
            "INSERT INTO logs (account_id, channel_id, message_id, status, error) "
            "VALUES (?, ?, ?, 'error', ?)",
            (account["id"], channel["id"], message["id"], f"DELETED: {e}"),
        )

    except FloodWait as e:
        wait_minutes = max(e.value // 60, 1)
        logger.warning(f"FloodWait: аккаунт #{account['id']}, отлёжка на {wait_minutes} мин")
        await execute(
            "UPDATE accounts SET cooldown_until = datetime('now', '+' || ? || ' minutes') WHERE id = ?",
            (wait_minutes, account["id"]),
        )

    except (PeerFlood, UserBannedInChannel) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен: {e}, отлёжка 24 ч")
        await execute(
            "UPDATE accounts SET status = 'cooldown', cooldown_until = datetime('now', '+24 hours') WHERE id = ?",
            (account["id"],),
        )
        await execute_returning(
            "INSERT INTO logs (account_id, channel_id, message_id, status, error) "
            "VALUES (?, ?, ?, 'error', ?)",
            (account["id"], channel["id"], message["id"], str(e)),
        )

    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await execute_returning(
            "INSERT INTO logs (account_id, channel_id, message_id, status, error) "
            "VALUES (?, ?, ?, 'error', ?)",
            (account["id"], channel["id"], message["id"], str(e)),
        )
