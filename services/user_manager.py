"""User lifecycle: creation, trial, entitlement checks."""
import logging
from db.database import execute, execute_returning, fetch_one

logger = logging.getLogger(__name__)


async def get_or_create_user(telegram_id: int, username: str = None,
                             first_name: str = None) -> dict:
    """Get existing user or create new one. Returns dict."""
    row = await fetch_one(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if row:
        # Update username/first_name if changed
        if (username and username != row["username"]) or \
           (first_name and first_name != row["first_name"]):
            await execute(
                "UPDATE users SET username = ?, first_name = ?, "
                "updated_at = datetime('now') WHERE telegram_id = ?",
                (username, first_name, telegram_id))
            row = await fetch_one(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return dict(row)

    await execute_returning(
        "INSERT INTO users (telegram_id, username, first_name) "
        "VALUES (?, ?, ?)",
        (telegram_id, username, first_name))
    row = await fetch_one(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return dict(row)


async def start_trial(telegram_id: int) -> dict:
    """Activate 24h trial. Only once per user."""
    user = await fetch_one(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not user:
        return {"ok": False, "error": "Пользователь не найден"}

    if user["trial_started_at"]:
        return {"ok": False, "error": "Пробный период уже был использован"}

    await execute(
        "UPDATE users SET status = 'trial_active', "
        "trial_started_at = datetime('now'), "
        "trial_expires_at = datetime('now', '+24 hours'), "
        "updated_at = datetime('now') "
        "WHERE telegram_id = ?",
        (telegram_id,))
    return {"ok": True}


async def check_entitlement(telegram_id: int) -> dict:
    """Check if user has active access.

    Returns: {"allowed": bool, "status": str, "expires_at": str|None}
    """
    user = await fetch_one(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not user:
        return {"allowed": False, "status": "unknown", "expires_at": None}

    status = user["status"]

    # Blocked users never pass
    if status == "blocked":
        return {"allowed": False, "status": "blocked", "expires_at": None}

    # Check active subscription first
    if status == "subscription_active":
        sub = await fetch_one(
            "SELECT expires_at FROM subscriptions "
            "WHERE user_telegram_id = ? AND status = 'active' "
            "ORDER BY expires_at DESC LIMIT 1",
            (telegram_id,))
        if sub:
            # Check if not expired
            expired = await fetch_one(
                "SELECT 1 WHERE datetime(?) < datetime('now')",
                (sub["expires_at"],))
            if expired:
                await execute(
                    "UPDATE users SET status = 'expired', "
                    "updated_at = datetime('now') WHERE telegram_id = ?",
                    (telegram_id,))
                return {"allowed": False, "status": "expired",
                        "expires_at": sub["expires_at"]}
            return {"allowed": True, "status": "subscription_active",
                    "expires_at": sub["expires_at"]}
        # No active sub found — mark expired
        await execute(
            "UPDATE users SET status = 'expired', "
            "updated_at = datetime('now') WHERE telegram_id = ?",
            (telegram_id,))
        return {"allowed": False, "status": "expired", "expires_at": None}

    # Check trial
    if status == "trial_active":
        expires = user["trial_expires_at"]
        if expires:
            expired = await fetch_one(
                "SELECT 1 WHERE datetime(?) < datetime('now')",
                (expires,))
            if expired:
                await execute(
                    "UPDATE users SET status = 'expired', "
                    "updated_at = datetime('now') WHERE telegram_id = ?",
                    (telegram_id,))
                return {"allowed": False, "status": "expired",
                        "expires_at": expires}
            return {"allowed": True, "status": "trial_active",
                    "expires_at": expires}

    # new or expired
    return {"allowed": False, "status": status, "expires_at": None}


async def block_user(telegram_id: int):
    await execute(
        "UPDATE users SET status = 'blocked', updated_at = datetime('now') "
        "WHERE telegram_id = ?", (telegram_id,))


async def unblock_user(telegram_id: int):
    await execute(
        "UPDATE users SET status = 'expired', updated_at = datetime('now') "
        "WHERE telegram_id = ?", (telegram_id,))
