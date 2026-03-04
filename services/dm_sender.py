import random
import asyncio
import logging
from pyrogram.errors import (
    FloodWait, PeerFlood, UserPrivacyRestricted,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked,
    UserAlreadyParticipant, InputUserDeactivated,
    UserIsBlocked, UserNotMutualContact, UserBannedInChannel,
)
from db.database import execute, fetch_one, fetch_all, execute_returning, delete_account
from services.account_manager import ensure_connected, disconnect
from services.spintax import spin

logger = logging.getLogger(__name__)


async def run_dm_campaign(campaign_id: int):
    """Запускает один цикл рассылки в ЛС для кампании.

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

    messages = await fetch_all("""
        SELECT m.* FROM messages m
        JOIN campaign_messages cm ON m.id = cm.message_id
        WHERE cm.campaign_id = ? AND m.is_active = 1
    """, (campaign_id,))

    if not accounts or not channels or not messages:
        logger.warning(f"Кампания DM #{campaign_id}: не хватает данных (аккаунты/каналы/сообщения)")
        return

    # Отфильтровываем аккаунты, у которых есть запас по лимитам
    available = [
        acc for acc in accounts
        if acc["comments_today"] < camp["daily_limit"]
        and acc["comments_hour"] < camp["hourly_limit"]
    ]
    if not available:
        logger.info(f"Кампания DM #{campaign_id}: все аккаунты достигли лимита")
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

    logger.info(f"Кампания DM #{campaign_id}: запуск {len(tasks)} аккаунтов параллельно, {len(channels)} каналов распределено")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.error(f"Кампания DM #{campaign_id}: воркер завершился с ошибкой: {result}")


async def _account_worker(account, channels, messages, camp):
    """Воркер одного аккаунта — проходит СВОИ каналы со своим КД."""
    for channel in channels:
        # Перепроверяем лимиты из БД
        acc_fresh = await fetch_one("SELECT * FROM accounts WHERE id = ?", (account["id"],))
        if not acc_fresh or acc_fresh["status"] != "active":
            break
        if acc_fresh["comments_today"] >= camp["daily_limit"]:
            break
        if acc_fresh["comments_hour"] >= camp["hourly_limit"]:
            break

        await _send_dm_from_channel(account, channel, messages, camp)

        delay = random.randint(
            max(camp["delay_min"], 90),
            max(camp["delay_max"], 180),
        )
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info(f"Кампания DM #{camp['id']}: аккаунт #{account['id']} прерван во время задержки")
            return


async def _collect_users_from_channel(client, channel_username: str, limit_posts: int = 5) -> list[int]:
    """Собирает user_id из комментариев к последним постам канала."""
    user_ids = set()
    channel_id = f"@{channel_username}"

    try:
        chat = await client.get_chat(channel_id)
        if not chat.linked_chat:
            logger.info(f"@{channel_username} не имеет группы обсуждений, пропускаю сбор юзеров")
            return []

        discussion_id = chat.linked_chat.id

        # Получаем последние посты
        post_count = 0
        async for post in client.get_chat_history(channel_id, limit=limit_posts):
            if not post.id:
                continue
            post_count += 1

            try:
                # Читаем комментарии к посту через discussion
                discussion_msg = await client.get_discussion_message(channel_id, post.id)
                async for reply in client.get_discussion_replies(
                    chat_id=discussion_id,
                    message_id=discussion_msg.id,
                    limit=50,
                ):
                    if reply.from_user and not reply.from_user.is_bot:
                        user_ids.add(reply.from_user.id)
            except Exception as e:
                logger.debug(f"Не удалось получить комментарии к посту {post.id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Ошибка сбора юзеров из @{channel_username}: {e}")

    logger.info(f"Собрано {len(user_ids)} юзеров из @{channel_username}")
    return list(user_ids)


async def _send_dm_from_channel(account, channel, messages, camp):
    """Отправляет ЛС юзерам из комментариев канала."""
    channel_username = channel["username"]
    mode = "dm"

    try:
        client = await ensure_connected(account)

        # 1. Подписываемся на канал
        try:
            await client.join_chat(f"@{channel_username}")
        except UserAlreadyParticipant:
            pass
        except Exception as e:
            logger.error(f"Не удалось подписаться на @{channel_username}: {e}")
            return

        # 2. Собираем юзеров из комментариев
        user_ids = await _collect_users_from_channel(client, channel_username)
        if not user_ids:
            logger.info(f"Нет юзеров для рассылки из @{channel_username}")
            return

        # Перемешиваем для рандомизации
        random.shuffle(user_ids)

        sent_count = 0
        for target_user_id in user_ids:
            # Проверяем лимиты аккаунта
            acc_fresh = await fetch_one("SELECT * FROM accounts WHERE id = ?", (account["id"],))
            if not acc_fresh or acc_fresh["status"] != "active":
                break
            if acc_fresh["comments_today"] >= camp["daily_limit"]:
                break
            if acc_fresh["comments_hour"] >= camp["hourly_limit"]:
                break

            # Проверяем, не писал ли ЛЮБОЙ аккаунт уже этому юзеру
            already_sent = await fetch_one(
                "SELECT 1 FROM logs WHERE target_user_id = ? AND mode = 'dm' AND status = 'sent'",
                (target_user_id,),
            )
            if already_sent:
                continue

            # Отправляем сообщение
            message = random.choice(messages)
            success = await _send_single_dm(client, account, channel, message, target_user_id, camp)

            if success:
                sent_count += 1

            # Задержка между сообщениями (увеличенная для безопасности)
            dm_delay = random.randint(
                max(camp["delay_min"], 60),
                max(camp["delay_max"], 180),
            )
            try:
                await asyncio.sleep(dm_delay)
            except asyncio.CancelledError:
                logger.info(f"DM рассылка прервана (shutdown), аккаунт #{account['id']} -> @{channel_username}")
                return

        logger.info(
            f"DM рассылка: аккаунт #{account['id']} -> @{channel_username}, "
            f"отправлено {sent_count} сообщений"
        )

    except asyncio.CancelledError:
        logger.info(f"DM рассылка прервана (shutdown), аккаунт #{account['id']} -> @{channel_username}")
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
        logger.error(f"Ошибка DM рассылки @{channel_username}: {e}")


async def _send_single_dm(client, account, channel, message, target_user_id: int, camp) -> bool:
    """Отправляет одно ЛС конкретному юзеру. Возвращает True при успехе."""
    mode = "dm"
    try:
        comment_text = spin(message["text"])
        await client.send_message(
            chat_id=target_user_id,
            text=comment_text,
        )

        # Обновляем счётчики
        await execute(
            "UPDATE accounts SET comments_today = comments_today + 1, "
            "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
            "WHERE id = ?",
            (account["id"],),
        )

        # Логируем успех
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, target_user_id, mode, status) "
            "VALUES (?, ?, ?, ?, ?, 'dm', 'sent')",
            (camp["id"], account["id"], channel["id"], message["id"], target_user_id),
        )

        logger.info(f"DM отправлено: аккаунт #{account['id']} -> user {target_user_id}")
        return True

    except FloodWait as e:
        logger.warning(f"FloodWait при DM: аккаунт #{account['id']}, ждём {e.value} сек")
        try:
            await asyncio.sleep(e.value)
        except asyncio.CancelledError:
            logger.info(f"FloodWait sleep прерван (shutdown), аккаунт #{account['id']}")
            raise
        return False

    except (PeerFlood, UserBannedInChannel) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен при DM: {e}")
        await execute(
            "UPDATE accounts SET status = 'limited' WHERE id = ?",
            (account["id"],),
        )
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, target_user_id, mode, status, error) "
            "VALUES (?, ?, ?, ?, ?, 'dm', 'error', ?)",
            (camp["id"], account["id"], channel["id"], message["id"], target_user_id, str(e)),
        )
        return False

    except (UserPrivacyRestricted, InputUserDeactivated, UserIsBlocked, UserNotMutualContact) as e:
        # Юзер закрыл ЛС или удалён — пропускаем, не ошибка аккаунта
        logger.info(f"DM недоступен для user {target_user_id}: {type(e).__name__}")
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, target_user_id, mode, status, error) "
            "VALUES (?, ?, ?, ?, ?, 'dm', 'skipped', ?)",
            (camp["id"], account["id"], channel["id"], message["id"], target_user_id, type(e).__name__),
        )
        return False

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв при DM ({type(e).__name__})")
        await disconnect(account["id"])
        await delete_account(account["id"])
        raise  # Пробрасываем наверх для остановки цикла

    except Exception as e:
        logger.error(f"Ошибка DM user {target_user_id}: {e}")
        await execute_returning(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, target_user_id, mode, status, error) "
            "VALUES (?, ?, ?, ?, ?, 'dm', 'error', ?)",
            (camp["id"], account["id"], channel["id"], message["id"], target_user_id, str(e)),
        )
        return False
