# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TelegramSMM — a Telegram bot for automating social media marketing campaigns. Admins manage Telegram accounts, target channels, message templates, and automated comment campaigns via the bot interface. Campaign execution uses real Telegram user accounts via Pyrogram (MTProto protocol).

**Language:** Python 3.11+
**Primary codebase language:** Russian (comments, UI text, variable names in some places)

## Running the Bot

```bash
# Install dependencies (use venv on modern Debian/Ubuntu)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set BOT_TOKEN, ADMIN_IDS, API_ID, API_HASH

# Run
python main.py
```

No build step, no test suite, no linter configured.

## Architecture

```
main.py                  → Entry point: init DB, register handlers, start scheduler, poll
core/config.py           → Loads .env vars (BOT_TOKEN, ADMIN_IDS, API_ID, API_HASH, DB_PATH)
core/scheduler.py        → APScheduler: runs campaigns every 5 min, resets hourly/daily limits
db/database.py           → Async SQLite helpers (execute, fetch_one, fetch_all, execute_returning)
db/models.py             → SQL schema string (8 tables, executed via executescript on startup)
bot/handlers/            → aiogram routers — one per feature area
bot/keyboards/inline.py  → Inline keyboard builder functions
services/                → Business logic that talks to Telegram via Pyrogram
sessions/                → Pyrogram .session files (gitignored)
```

### Request flow

1. User interacts with bot → aiogram dispatcher routes to handler in `bot/handlers/`
2. Handlers use FSM states (aiogram `StatesGroup`) for multi-step flows (add account, auth, search channels, etc.)
3. Handlers read/write SQLite via `db/database.py` helper functions (raw SQL, no ORM)
4. `core/scheduler.py` triggers `services/commenter.run_campaign()` every 5 minutes for active campaigns
5. `services/commenter.py` picks accounts (lowest daily count first), selects random message, sends via Pyrogram, logs result
6. `services/account_manager.py` manages Pyrogram client lifecycle (connect, auth with phone code, disconnect)
7. `services/channel_parser.py` searches channels via Pyrogram's `search_global`

### Database

SQLite file `data.db` (path in `core/config.DB_PATH`). Schema in `db/models.py`. All queries are raw SQL strings passed to `aiosqlite`. Each database call opens a new connection (no connection pooling).

**Tables:** accounts, channels, messages, campaigns, campaign_channels, campaign_accounts, campaign_messages, logs.

Junction tables (campaign_channels, campaign_accounts, campaign_messages) link campaigns to their assigned resources.

### Key patterns

- **Admin-only access:** Handlers check `user_id in ADMIN_IDS` from config
- **FSM states:** Each handler module defines its own `StatesGroup` for conversational flows
- **Callback data prefixes:** Handlers use string prefixes like `acc_`, `ch_`, `camp_`, `msg_` for routing inline button callbacks
- **Account selection strategy:** Campaign runner picks account with the lowest `comments_today` that hasn't exceeded hourly/daily limits
- **FloodWait handling:** `commenter.py` catches Pyrogram's `FloodWait` and pauses; marks accounts as `'limited'` on repeated errors
- **Rate limit resets:** Scheduler resets `comments_hour` every hour (cron minute=0) and `comments_today` + `comments_hour` daily at midnight

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram Bot API token |
| `ADMIN_IDS` | Comma-separated Telegram user IDs with admin access |
| `API_ID` | Telegram API ID from my.telegram.org (for Pyrogram) |
| `API_HASH` | Telegram API Hash from my.telegram.org (for Pyrogram) |
