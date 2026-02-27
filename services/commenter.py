import random
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram.errors import (
    FloodWait, PeerFlood, UserBannedInChannel,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan,
    UserAlreadyParticipant, ChannelPrivate, InviteRequestSent,
)
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
    accounts = await fetch_all("""
        SELECT a.* FROM accounts a
        JOIN campaign_accounts ca ON a.id = ca.account_id
        WHERE ca.campaign_id = ? AND a.status = 'active'
    """, (campaign_id,))

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

    if not accounts or not channels or not messages:
        logger.warning(f"Кампания #{campaign_id}: не хватает данных (аккаунты/каналы/сообщения)")
        return

    for channel in channels:
        # Выбираем аккаунт с наименьшей нагрузкой
        account = await _pick_account(accounts, camp)
        if not account:
            logger.info(f"Кампания #{campaign_id}: все аккаунты достигли лимита")
            break

        # Выбираем случайное сообщение
        message = random.choice(messages)

        # Отправляем комментарий
        await _send_comment(account, channel, message, camp)

        # Случайная задержка
        delay = random.randint(camp["delay_min"], camp["delay_max"])
        await asyncio.sleep(delay)


async def _pick_account(accounts: list, camp) -> dict | None:
    """Выбирает аккаунт, который ещё не достиг лимитов."""
    available = []
    for acc in accounts:
        # Проверяем дневной лимит
        if acc["comments_today"] >= camp["daily_limit"]:
            continue
        # Проверяем часовой лимит
        if acc["comments_hour"] >= camp["hourly_limit"]:
            continue
        available.append(acc)

    if not available:
        return None

    # Выбираем аккаунт с наименьшим количеством комментариев за сегодня
    return min(available, key=lambda a: a["comments_today"])


async def _send_comment(account, channel, message, camp):
    """Отправляет комментарий в канал от имени аккаунта."""
    try:
        client = await ensure_connected(account)

        # Подписываемся на канал, если ещё не подписаны
        try:
            await client.join_chat(f"@{channel['username']}")
            logger.info(f"Аккаунт #{account['id']} подписался на @{channel['username']}")
        except UserAlreadyParticipant:
            pass
        except InviteRequestSent:
            logger.warning(f"@{channel['username']} требует одобрения заявки, пропускаю")
            return
        except ChannelPrivate:
            logger.warning(f"@{channel['username']} — приватный канал, пропускаю")
            return

        # Подписываемся на группу обсуждений (комментарии идут туда)
        try:
            chat = await client.get_chat(f"@{channel['username']}")
            if chat.linked_chat:
                try:
                    await client.join_chat(chat.linked_chat.id)
                    logger.info(
                        f"Аккаунт #{account['id']} вступил в группу обсуждений "
                        f"канала @{channel['username']} (id={chat.linked_chat.id})"
                    )
                except UserAlreadyParticipant:
                    pass
            else:
                logger.warning(f"@{channel['username']} не имеет группы обсуждений, пропускаю")
                return
        except Exception as e:
            logger.warning(f"Не удалось получить группу обсуждений @{channel['username']}: {e}")
            return

        # Получаем последний пост канала
        channel_id = f"@{channel['username']}"
        async for post in client.get_chat_history(channel_id, limit=1):
            if not post.id:
                break

            # Получаем зеркальный пост в группе обсуждений
            discussion_msg = await client.get_discussion_message(channel_id, post.id)

            # Обрабатываем spintax и отправляем комментарий в группу обсуждений
            comment_text = spin(message["text"])
            await client.send_message(
                chat_id=discussion_msg.chat.id,
                text=comment_text,
                reply_to_message_id=discussion_msg.id,
            )

            # Обновляем счётчики
            await execute(
                "UPDATE accounts SET comments_today = comments_today + 1, "
                "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
                "WHERE id = ?",
                (account["id"],),
            )

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
        logger.warning(f"FloodWait: аккаунт #{account['id']}, ждём {e.value} сек")
        await asyncio.sleep(e.value)

    except (PeerFlood, UserBannedInChannel) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен: {e}")
        await execute(
            "UPDATE accounts SET status = 'limited' WHERE id = ?",
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
