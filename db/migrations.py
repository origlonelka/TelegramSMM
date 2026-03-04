"""Versioned database migration system."""
import logging

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Migration 1: admins + audit_logs (Sprint 1 — SEC-03)
    [
        """CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            role TEXT NOT NULL DEFAULT 'admin',
            is_active INTEGER DEFAULT 1,
            added_by INTEGER,
            added_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_user_id)",
    ],
    # Migration 2: proxy columns (Sprint 1 — REL-04)
    [
        "ALTER TABLE proxies ADD COLUMN last_error TEXT",
        "ALTER TABLE proxies ADD COLUMN latency_ms INTEGER",
    ],
    # Migration 3: logs.target_user_id (ранее inline-миграции)
    [
        "ALTER TABLE accounts ADD COLUMN proxy TEXT",
        "ALTER TABLE campaigns ADD COLUMN mode TEXT DEFAULT 'comments'",
        "ALTER TABLE logs ADD COLUMN mode TEXT",
        "ALTER TABLE logs ADD COLUMN target_user_id INTEGER",
        "ALTER TABLE logs ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id)",
    ],
    # Migration 4: users table (Sprint 2 — BIZ-01)
    [
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            trial_started_at TEXT,
            trial_expires_at TEXT,
            referrer_telegram_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_users_tgid ON users(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)",
    ],
    # Migration 5: owner_user_id on business tables (Sprint 2)
    [
        "ALTER TABLE accounts ADD COLUMN owner_user_id INTEGER",
        "ALTER TABLE channels ADD COLUMN owner_user_id INTEGER",
        "ALTER TABLE messages ADD COLUMN owner_user_id INTEGER",
        "ALTER TABLE campaigns ADD COLUMN owner_user_id INTEGER",
        "ALTER TABLE presets ADD COLUMN owner_user_id INTEGER",
    ],
]


async def run_migrations(db):
    """Run all pending migrations."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    await db.commit()

    cursor = await db.execute("SELECT MAX(version) as v FROM schema_version")
    result = await cursor.fetchone()
    current = result[0] if result and result[0] else 0

    for i, statements in enumerate(MIGRATIONS, start=1):
        if i <= current:
            continue
        logger.info(f"Applying migration {i}...")
        for sql in statements:
            sql = sql.strip()
            if not sql:
                continue
            try:
                await db.execute(sql)
            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate column" in err_msg or "already exists" in err_msg:
                    continue
                raise
        await db.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (i,))
        await db.commit()
        logger.info(f"Migration {i} applied")


async def seed_superadmins(db, superadmin_ids: list[int]):
    """Insert SUPERADMIN_IDS into admins table if not already present."""
    for uid in superadmin_ids:
        existing = await db.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (uid,))
        row = await existing.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO admins (user_id, role) VALUES (?, 'superadmin')",
                (uid,))
    await db.commit()
