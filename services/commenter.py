import random
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram.errors import (
    FloodWait, PeerFlood, UserBannedInChannel,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked,
    UserAlreadyParticipant, ChannelPrivate, InviteRequestSent,
)
from db.database import execute, fetch_one, fetch_all, execute_returning, delete_account
from services.account_manager import ensure_connected, disconnect
from services.spintax import spin

logger = logging.getLogger(__name__)


async def run_campaign(campaign_id: int):
    """Запускает один цикл рассылки для кампании.

    Каждый аккаунт работает параллельно со своим КД.
    """
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

    # Отфильтровываем аккаунты, у которых есть запас по лимитам
    available = [
        acc for acc in accounts
        if acc["comments_today"] < camp["daily_limit"]
        and acc["comments_hour"] < camp["hourly_limit"]
    ]
    if not available:
        logger.info(f"Кампания #{campaign_id}: все аккаунты достигли лимита")
        return

    # Распределяем каналы между аккаунтами (round-robin)
    shuffled_channels = list(channels)
    random.shuffle(shuffled_channels)
    buckets: dict[int, list] = {acc["id"]: [] for acc in available}
    for i, channel in enumerate(shuffled_channels):
        acc = available[i % len(available)]
        buckets[acc["id"]].append(channel)

    # Запускаем параллельного воркера на каждый аккаунт
    tasks = []
    for account in available:
        acc_channels = buckets[account["id"]]
        if acc_channels:
            tasks.append(_account_worker(account, acc_channels, messages, camp))

    logger.info(f"Кампания #{campaign_id}: запуск {len(tasks)} аккаунтов параллельно, {len(channels)} каналов распределено")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.error(f"Кампания #{campaign_id}: воркер аккаунта завершился с ошибкой: {result}")


async def _account_worker(account, channels, messages, camp):
    """Воркер одного аккаунта — проходит СВОИ каналы со своим КД."""
    mode = camp["mode"] or "comments"

    for channel in channels:
        # Перепроверяем лимиты из БД
        acc_fresh = await fetch_one("SELECT * FROM accounts WHERE id = ?", (account["id"],))
        if not acc_fresh or acc_fresh["status"] != "active":
            break
        if acc_fresh["comments_today"] >= camp["daily_limit"]:
            break
        if acc_fresh["comments_hour"] >= camp["hourly_limit"]:
            break

        message = random.choice(messages)
        await _send_comment(account, channel, message, camp, mode)

        # Свой КД для этого аккаунта
        delay = random.randint(
            max(camp["delay_min"], 90),
            max(camp["delay_max"], 180),
        )
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info(f"Кампания #{camp['id']}: аккаунт #{account['id']} прерван во время задержки")
            return


async def _send_comment(account, channel, message, camp, mode="comments"):
    """Отправляет комментарий в канал от имени аккаунта."""
    channel_username = channel['username']
    logger.info(f"[v2] _send_comment: аккаунт #{account['id']} -> @{channel_username}")

    try:
        client = await ensure_connected(account)

        # 1. Подписываемся на канал
        try:
            await client.join_chat(f"@{channel_username}")
            logger.info(f"Аккаунт #{account['id']} подписался на @{channel_username}")
        except UserAlreadyParticipant:
            logger.info(f"Аккаунт #{account['id']} уже подписан на @{channel_username}")
        except Exception as e:
            logger.error(f"Не удалось подписаться на @{channel_username}: {type(e).__name__}: {e}")
            return

        # 2. Подписываемся на группу обсуждений (комментарии идут туда)
        try:
            chat = await client.get_chat(f"@{channel_username}")
            if chat.linked_chat:
                try:
                    await client.join_chat(chat.linked_chat.id)
                    logger.info(
                        f"Аккаунт #{account['id']} вступил в группу обсуждений "
                        f"@{channel_username} (id={chat.linked_chat.id})"
                    )
                except UserAlreadyParticipant:
                    logger.info(f"Аккаунт #{account['id']} уже в группе обсуждений @{channel_username}")
                except Exception as e:
                    logger.error(f"Не удалось вступить в группу обсуждений @{channel_username}: {type(e).__name__}: {e}")
            else:
                logger.warning(f"@{channel_username} не имеет группы обсуждений, пропускаю")
                return
        except Exception as e:
            logger.error(f"Не удалось получить инфо о @{channel_username}: {type(e).__name__}: {e}")
            return

        # 3. Получаем последний пост и отправляем комментарий
        channel_id = f"@{channel_username}"
        async for post in client.get_chat_history(channel_id, limit=1):
            if not post.id:
                break

            # Проверяем, не комментировал ли ЛЮБОЙ аккаунт уже этот пост
            already_commented = await fetch_one(
                "SELECT 1 FROM logs WHERE channel_id = ? AND post_id = ? AND mode = ? AND status = 'sent'",
                (channel["id"], post.id, mode),
            )
            if already_commented:
                logger.info(
                    f"Пост {post.id} в @{channel_username} уже прокомментирован, пропускаю"
                )
                break

            # Получаем зеркальный пост в группе обсуждений
            discussion_msg = await client.get_discussion_message(channel_id, post.id)
            logger.info(
                f"Discussion message: chat_id={discussion_msg.chat.id}, "
                f"msg_id={discussion_msg.id} для поста {post.id}"
            )

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
                "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, post_id, mode, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'sent')",
                (camp["id"], account["id"], channel["id"], message["id"], post.id, mode),
            )

            logger.info(
                f"Комментарий отправлен: аккаунт #{account['id']} -> "
                f"@{channel['username']} (пост {post.id})"
            )
            break

    except asyncio.CancelledError:
        logger.info(f"Отправка комментария прервана (shutdown), аккаунт #{account['id']} -> @{channel_username}")
        raise

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв ({type(e).__name__}), удаляю")
        await disconnect(account["id"])
        await delete_account(account["id"])
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, mode, status, error) "
            "VALUES (?, ?, ?, ?, ?, 'error', ?)",
            (camp["id"], account["id"], channel["id"], message["id"], mode, f"DELETED: {e}"),
        )

    except FloodWait as e:
        logger.warning(f"FloodWait: аккаунт #{account['id']}, ждём {e.value} сек")
        try:
            await asyncio.sleep(e.value)
        except asyncio.CancelledError:
            logger.info(f"FloodWait sleep прерван (shutdown), аккаунт #{account['id']}")
            return

    except (PeerFlood, UserBannedInChannel) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен: {e}")
        await execute(
            "UPDATE accounts SET status = 'limited' WHERE id = ?",
            (account["id"],),
        )
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, mode, status, error) "
            "VALUES (?, ?, ?, ?, ?, 'error', ?)",
            (camp["id"], account["id"], channel["id"], message["id"], mode, str(e)),
        )

    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, mode, status, error) "
            "VALUES (?, ?, ?, ?, ?, 'error', ?)",
            (camp["id"], account["id"], channel["id"], message["id"], mode, str(e)),
        )
