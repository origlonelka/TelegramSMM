SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    api_id INTEGER NOT NULL,
    api_hash TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    post_id INTEGER,
    status TEXT DEFAULT 'sent',
    error TEXT,
    sent_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (channel_id) REFERENCES channels(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
"""
