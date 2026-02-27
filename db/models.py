SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    api_id INTEGER NOT NULL,
    api_hash TEXT NOT NULL,
    proxy TEXT,
    session_file TEXT,
    status TEXT DEFAULT 'inactive',
    comments_today INTEGER DEFAULT 0,
    comments_hour INTEGER DEFAULT 0,
    last_comment_at TEXT,
    added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    title TEXT,
    has_comments INTEGER DEFAULT 1,
    added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mode TEXT DEFAULT 'comments',
    is_active INTEGER DEFAULT 0,
    delay_min INTEGER DEFAULT 60,
    delay_max INTEGER DEFAULT 300,
    hourly_limit INTEGER DEFAULT 5,
    daily_limit INTEGER DEFAULT 30,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaign_channels (
    campaign_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, channel_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_accounts (
    campaign_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, account_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_messages (
    campaign_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, message_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS account_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    bio TEXT,
    photo_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    template_id INTEGER,
    campaign_id INTEGER,
    mode TEXT DEFAULT 'comments',
    delay_min INTEGER DEFAULT 60,
    delay_max INTEGER DEFAULT 300,
    hourly_limit INTEGER DEFAULT 5,
    daily_limit INTEGER DEFAULT 30,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (template_id) REFERENCES account_templates(id) ON DELETE SET NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS preset_channels (
    preset_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (preset_id, channel_id),
    FOREIGN KEY (preset_id) REFERENCES presets(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS preset_messages (
    preset_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (preset_id, message_id),
    FOREIGN KEY (preset_id) REFERENCES presets(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    type TEXT DEFAULT 'socks5',
    status TEXT DEFAULT 'unchecked',
    response_time INTEGER,
    account_id INTEGER,
    last_checked_at TEXT,
    added_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    post_id INTEGER,
    mode TEXT,
    status TEXT DEFAULT 'sent',
    error TEXT,
    sent_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (channel_id) REFERENCES channels(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
"""
