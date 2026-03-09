import aiosqlite
from core.config import DB_PATH, SUPERADMIN_IDS
from db.models import SCHEMA

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _db.execute("PRAGMA busy_timeout=5000")
    return _db


async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA)

    # Versioned migrations
    from db.migrations import run_migrations, seed_superadmins
    await run_migrations(db)

    # Seed superadmins from .env on every startup
    if SUPERADMIN_IDS:
        await seed_superadmins(db, SUPERADMIN_IDS)

    # One-time data fix: CTA → comments
    for fix in [
        "UPDATE campaigns SET mode = 'comments' WHERE mode = 'comments_cta'",
        "UPDATE presets SET mode = 'comments' WHERE mode = 'comments_cta'",
    ]:
        try:
            await db.execute(fix)
        except Exception:
            pass
    await db.commit()


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def execute(query: str, params: tuple = ()):
    db = await get_db()
    await db.execute(query, params)
    await db.commit()


async def fetch_one(query: str, params: tuple = ()):
    db = await get_db()
    cursor = await db.execute(query, params)
    return await cursor.fetchone()


async def fetch_all(query: str, params: tuple = ()):
    db = await get_db()
    cursor = await db.execute(query, params)
    return await cursor.fetchall()


async def delete_account(acc_id: int):
    """Удаляет аккаунт и все его связи. Prefer hard_delete_account() from account_manager."""
    from services.account_manager import hard_delete_account
    await hard_delete_account(acc_id)


async def execute_returning(query: str, params: tuple = ()):
    db = await get_db()
    cursor = await db.execute(query, params)
    await db.commit()
    return cursor.lastrowid


async def execute_no_fk(query: str, params: tuple = ()):
    """Execute with foreign keys temporarily disabled (for cross-table refs like promo_chats logs)."""
    db = await get_db()
    await db.execute("PRAGMA foreign_keys=OFF")
    try:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.execute("PRAGMA foreign_keys=ON")
