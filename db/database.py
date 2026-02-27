import aiosqlite
from core.config import DB_PATH
from db.models import SCHEMA

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA)
    # Миграция: добавить proxy если его нет
    try:
        await db.execute("ALTER TABLE accounts ADD COLUMN proxy TEXT")
    except Exception:
        pass  # колонка уже существует
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


async def execute_returning(query: str, params: tuple = ()):
    db = await get_db()
    cursor = await db.execute(query, params)
    await db.commit()
    return cursor.lastrowid
