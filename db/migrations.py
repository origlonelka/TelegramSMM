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
    # Migration 6: subscription_plans + subscriptions (Sprint 3 — Payments)
    [
        """CREATE TABLE IF NOT EXISTS subscription_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            price_rub INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_telegram_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            payment_id TEXT UNIQUE,
            yookassa_payment_id TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            amount_rub INTEGER NOT NULL,
            started_at TEXT,
            expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_telegram_id) REFERENCES users(telegram_id),
            FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status)",
        "CREATE INDEX IF NOT EXISTS idx_sub_yookassa ON subscriptions(yookassa_payment_id)",
        """INSERT OR IGNORE INTO subscription_plans (code, name, duration_days, price_rub)
           VALUES ('monthly', 'Месяц', 30, 990)""",
        """INSERT OR IGNORE INTO subscription_plans (code, name, duration_days, price_rub)
           VALUES ('quarterly', '3 месяца', 90, 2490)""",
        """INSERT OR IGNORE INTO subscription_plans (code, name, duration_days, price_rub)
           VALUES ('yearly', 'Год', 365, 7990)""",
    ],
    # Migration 7: admin panel tables (Sprint 4 — ADM)
    [
        """CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL DEFAULT 'discount',
            value REAL NOT NULL,
            max_uses INTEGER DEFAULT 0,
            uses_count INTEGER DEFAULT 0,
            valid_until TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS promo_activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_code_id INTEGER NOT NULL,
            user_telegram_id INTEGER NOT NULL,
            activated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(promo_code_id, user_telegram_id)
        )""",
        """CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_telegram_id INTEGER NOT NULL,
            referred_telegram_id INTEGER UNIQUE NOT NULL,
            bonus_days INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_telegram_id INTEGER NOT NULL,
            subject TEXT,
            status TEXT DEFAULT 'open',
            assigned_to INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_telegram_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE
        )""",
    ],
    # Migration 8: promo chats (Sprint 5 — CHAT-01)
    [
        """CREATE TABLE IF NOT EXISTS promo_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            username TEXT,
            title TEXT,
            min_delay INTEGER DEFAULT 300,
            max_delay INTEGER DEFAULT 600,
            max_posts_per_hour INTEGER DEFAULT 3,
            max_posts_per_day INTEGER DEFAULT 10,
            dedup_window_hours INTEGER DEFAULT 24,
            is_active INTEGER DEFAULT 1,
            allow_posting INTEGER DEFAULT 1,
            error_count INTEGER DEFAULT 0,
            last_post_at TEXT,
            owner_user_id INTEGER,
            added_at TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_promo_active ON promo_chats(is_active, allow_posting)",
        """CREATE TABLE IF NOT EXISTS campaign_promo_chats (
            campaign_id INTEGER NOT NULL,
            promo_chat_id INTEGER NOT NULL,
            PRIMARY KEY (campaign_id, promo_chat_id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
            FOREIGN KEY (promo_chat_id) REFERENCES promo_chats(id) ON DELETE CASCADE
        )""",
        "ALTER TABLE campaigns ADD COLUMN is_dry_run INTEGER DEFAULT 0",
    ],
    # Migration 9: Boost (накрутка) — баланс, заказы, сервисы
    [
        "ALTER TABLE users ADD COLUMN balance_rub REAL DEFAULT 0",
        """CREATE TABLE IF NOT EXISTS boost_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_telegram_id INTEGER NOT NULL,
            likedrom_order_id INTEGER,
            service_id INTEGER NOT NULL,
            service_name TEXT,
            link TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price_rub REAL NOT NULL,
            cost_rub REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_boost_orders_user ON boost_orders(user_telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_boost_orders_status ON boost_orders(status)",
        """CREATE TABLE IF NOT EXISTS balance_topups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_telegram_id INTEGER NOT NULL,
            amount_rub REAL NOT NULL,
            yookassa_payment_id TEXT UNIQUE,
            payment_uuid TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_topups_user ON balance_topups(user_telegram_id)",
        """CREATE TABLE IF NOT EXISTS boost_services (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            network TEXT,
            min_qty INTEGER,
            max_qty INTEGER,
            cost_per_1k REAL,
            price_per_1k REAL,
            is_active INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_boost_svc_net ON boost_services(network, is_active)",
    ],
    # Migration 10: add category_id to boost_services
    [
        "ALTER TABLE boost_services ADD COLUMN category_id INTEGER DEFAULT 0",
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
