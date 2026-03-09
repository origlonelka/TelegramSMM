"""Promo chat posting campaign engine.

Sends messages to whitelisted promo/advertising chats.
Pattern mirrors commenter.py with per-chat limits, dedup, and anti-ban.
"""
import random
import asyncio
import logging
from datetime import datetime

from pyrogram.errors import (
    FloodWait, PeerFlood, UserBannedInChannel,
    AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan, SessionRevoked,
    ChatWriteForbidden, SlowmodeWait,
)
from db.database import execute, fetch_one, fetch_all, execute_returning, execute_no_fk, delete_account
from services.account_manager import ensure_connected, disconnect
from services.spintax import spin

logger = logging.getLogger(__name__)


async def run_promo_chat_campaign(campaign_id: int):
    """Run one cycle of promo chat posting for a campaign."""
    camp_row = await fetch_one(
        "SELECT * FROM campaigns WHERE id = ? AND is_active = 1",
        (campaign_id,))
    if not camp_row:
        return
    camp = dict(camp_row)

    accounts = await fetch_all("""
        SELECT a.* FROM accounts a
        JOIN campaign_accounts ca ON a.id = ca.account_id
        WHERE ca.campaign_id = ? AND a.status = 'active'
    """, (campaign_id,))

    promo_chats = await fetch_all("""
        SELECT pc.* FROM promo_chats pc
        JOIN campaign_promo_chats cpc ON pc.id = cpc.promo_chat_id
        WHERE cpc.campaign_id = ? AND pc.is_active = 1 AND pc.allow_posting = 1
    """, (campaign_id,))

    messages = await fetch_all("""
        SELECT m.* FROM messages m
        JOIN campaign_messages cm ON m.id = cm.message_id
        WHERE cm.campaign_id = ? AND m.is_active = 1
    """, (campaign_id,))

    if not accounts or not promo_chats or not messages:
        logger.warning(
            f"Промо-кампания #{campaign_id}: не хватает данных")
        return

    available = [
        acc for acc in accounts
        if acc["comments_today"] < camp["daily_limit"]
        and acc["comments_hour"] < camp["hourly_limit"]
    ]
    if not available:
        logger.info(f"Промо-кампания #{campaign_id}: все аккаунты на лимите")
        return

    # Filter chats exceeding per-chat limits
    eligible_chats = []
    for chat in promo_chats:
        hour_count = await fetch_one(
            "SELECT COUNT(*) as c FROM logs WHERE channel_id = ? AND mode = 'promo_chats' "
            "AND status = 'sent' AND sent_at >= datetime('now', '-1 hour')",
            (chat["id"],))
        day_count = await fetch_one(
            "SELECT COUNT(*) as c FROM logs WHERE channel_id = ? AND mode = 'promo_chats' "
            "AND status = 'sent' AND sent_at >= datetime('now', '-24 hours')",
            (chat["id"],))
        if (hour_count["c"] < chat["max_posts_per_hour"]
                and day_count["c"] < chat["max_posts_per_day"]):
            eligible_chats.append(chat)

    if not eligible_chats:
        logger.info(f"Промо-кампания #{campaign_id}: все чаты на лимите")
        return

    # Round-robin distribution
    random.shuffle(eligible_chats)
    buckets: dict[int, list] = {acc["id"]: [] for acc in available}
    for i, chat in enumerate(eligible_chats):
        acc = available[i % len(available)]
        buckets[acc["id"]].append(chat)

    tasks = []
    for account in available:
        acc_chats = buckets[account["id"]]
        if acc_chats:
            tasks.append(
                _promo_worker(account, acc_chats, messages, camp))

    logger.info(
        f"Промо-кампания #{campaign_id}: {len(tasks)} аккаунтов, "
        f"{len(eligible_chats)} чатов")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"Промо-воркер #{i} упал: {type(r).__name__}: {r}")


async def _promo_worker(account, chats, messages, camp):
    """Worker for one account — posts to assigned promo chats."""
    logger.info(f"[promo] воркер #{account['id']} стартует, чатов: {len(chats)}")
    for chat in chats:
        acc_fresh = await fetch_one(
            "SELECT * FROM accounts WHERE id = ?", (account["id"],))
        if not acc_fresh or acc_fresh["status"] != "active":
            logger.info(f"[promo] аккаунт #{account['id']} неактивен, стоп")
            break
        if acc_fresh["comments_today"] >= camp["daily_limit"]:
            logger.info(f"[promo] аккаунт #{account['id']} дневной лимит")
            break
        if acc_fresh["comments_hour"] >= camp["hourly_limit"]:
            logger.info(f"[promo] аккаунт #{account['id']} часовой лимит")
            break

        message = random.choice(messages)
        try:
            await _send_promo_message(account, chat, message, camp)
        except Exception as e:
            logger.error(f"[promo] _send_promo_message упал: {type(e).__name__}: {e}")

        delay = random.randint(
            max(chat["min_delay"], 60),
            max(chat["max_delay"], 120))
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return


async def _send_promo_message(account, chat, message, camp):
    """Send a single promo message to a chat."""
    chat_target = f"@{chat['username']}" if chat["username"] else chat["chat_id"]
    logger.info(
        f"[promo] аккаунт #{account['id']} -> {chat_target}")


    # Dry run
    if camp.get("is_dry_run"):
        await execute_no_fk(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, "
            "mode, status) VALUES (?, ?, ?, ?, 'promo_chats', 'dry_run')",
            (camp["id"], account["id"], chat["id"], message["id"]))
        logger.info(f"[promo] dry_run: аккаунт #{account['id']} -> {chat_target}")
        return

    try:
        client = await ensure_connected(account)

        # Join chat if needed
        try:
            await client.join_chat(str(chat_target))
        except Exception:
            pass

        # Apply UTM variables
        text = spin(message["text"])
        text = text.replace("{utm_source}", "promo_chat")
        text = text.replace("{utm_campaign}", str(camp["id"]))
        text = text.replace("{utm_account}", str(account["id"]))

        await client.send_message(chat_id=chat_target, text=text)

        # Update counters
        await execute(
            "UPDATE accounts SET comments_today = comments_today + 1, "
            "comments_hour = comments_hour + 1, last_comment_at = datetime('now') "
            "WHERE id = ?", (account["id"],))

        await execute(
            "UPDATE promo_chats SET last_post_at = datetime('now'), "
            "error_count = 0 WHERE id = ?", (chat["id"],))

        await execute_no_fk(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, "
            "mode, status) VALUES (?, ?, ?, ?, 'promo_chats', 'sent')",
            (camp["id"], account["id"], chat["id"], message["id"]))

        logger.info(f"[promo] отправлено: аккаунт #{account['id']} -> {chat_target}")

    except asyncio.CancelledError:
        raise

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan,
            SessionRevoked) as e:
        logger.error(f"Аккаунт #{account['id']} мёртв ({type(e).__name__})")
        await disconnect(account["id"])
        await delete_account(account["id"])
        await execute_no_fk(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, "
            "mode, status, error) VALUES (?, ?, ?, ?, 'promo_chats', 'error', ?)",
            (camp["id"], account["id"], chat["id"], message["id"],
             f"DELETED: {e}"))

    except FloodWait as e:
        logger.warning(f"FloodWait: аккаунт #{account['id']}, {e.value} сек")
        try:
            await asyncio.sleep(e.value)
        except asyncio.CancelledError:
            return

    except SlowmodeWait as e:
        logger.warning(f"SlowmodeWait: чат {chat_target}, {e.value} сек")
        await execute(
            "UPDATE promo_chats SET error_count = error_count + 1 WHERE id = ?",
            (chat["id"],))

    except (PeerFlood, UserBannedInChannel, ChatWriteForbidden) as e:
        logger.error(f"Аккаунт #{account['id']} ограничен в {chat_target}: {e}")
        await execute(
            "UPDATE accounts SET status = 'limited' WHERE id = ?",
            (account["id"],))
        # Disable chat posting after 5 errors
        new_count = await fetch_one(
            "SELECT error_count FROM promo_chats WHERE id = ?",
            (chat["id"],))
        if new_count and new_count["error_count"] >= 5:
            await execute(
                "UPDATE promo_chats SET allow_posting = 0 WHERE id = ?",
                (chat["id"],))
            logger.warning(f"Чат {chat_target} отключён (>5 ошибок)")
        else:
            await execute(
                "UPDATE promo_chats SET error_count = error_count + 1 "
                "WHERE id = ?", (chat["id"],))
        await execute_no_fk(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, "
            "mode, status, error) VALUES (?, ?, ?, ?, 'promo_chats', 'error', ?)",
            (camp["id"], account["id"], chat["id"], message["id"], str(e)))

    except Exception as e:
        logger.error(f"[promo] ошибка: {e}")
        await execute(
            "UPDATE promo_chats SET error_count = error_count + 1 WHERE id = ?",
            (chat["id"],))
        await execute_no_fk(
            "INSERT INTO logs (campaign_id, account_id, channel_id, message_id, "
            "mode, status, error) VALUES (?, ?, ?, ?, 'promo_chats', 'error', ?)",
            (camp["id"], account["id"], chat["id"], message["id"], str(e)))
