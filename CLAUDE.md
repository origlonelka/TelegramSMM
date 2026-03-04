# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TelegramSMM — a Telegram bot for automating social media marketing campaigns. Admins manage Telegram accounts, target channels, message templates, and automated comment campaigns via the bot interface. Campaign execution uses real Telegram user accounts via Pyrogram (MTProto protocol).

**Language:** Python 3.11+
**Primary codebase language:** Russian (comments, UI text, variable names in some places)

## Running the Bot

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: set BOT_TOKEN, ADMIN_IDS, ADMIN_USERNAMES, API_ID, API_HASH

python main.py
```

No build step, no test suite, no linter configured.

## Architecture

### Startup flow (`main.py`)

1. `init_db()` — runs `executescript(SCHEMA)` from `db/models.py`, applies migrations (e.g., proxy column)
2. Creates `Bot` + `Dispatcher` with `MemoryStorage` (FSM state is in-memory, lost on restart)
3. Registers `AccessMiddleware` on both `message` and `callback_query` — checks `user.id in ADMIN_IDS`
4. Includes routers in order: start → accounts → channels → messages → campaigns → settings
5. `start_scheduler()` — starts APScheduler
6. `dp.start_polling(bot)` — blocks until shutdown; `close_db()` on exit

### Layer responsibilities

- **`bot/handlers/`** — aiogram routers, one per feature. Each defines its own `StatesGroup` for FSM flows. Handlers do input validation and call into `services/` or `db/database.py`.
- **`bot/keyboards/inline.py`** — 30+ builder functions returning `InlineKeyboardMarkup`. All callback data uses prefixed IDs: `acc_view_{id}`, `camp_ch_toggle_{camp_id}_{ch_id}`, `msg_del_confirm_{id}`, etc.
- **`services/`** — business logic layer. Talks to Telegram via Pyrogram and to SQLite via `db/database.py`. No aiogram dependency.
- **`db/database.py`** — thin async wrapper over `aiosqlite`. Each call opens a new connection (no pooling). Enables WAL mode and foreign keys on every connection.
- **`db/models.py`** — single `SCHEMA` string with 8 `CREATE TABLE IF NOT EXISTS` statements executed via `executescript`.

### Scheduler jobs (`core/scheduler.py`)

Three APScheduler jobs on `AsyncIOScheduler`:
- **Campaign runner** — `IntervalTrigger(minutes=5)`: fetches active campaigns, calls `run_campaign()` for each
- **Hourly reset** — `CronTrigger(minute=0)`: `UPDATE accounts SET comments_hour = 0`
- **Daily reset** — `CronTrigger(hour=0, minute=0)`: resets both `comments_today` and `comments_hour`

### Database tables

8 tables in SQLite (`data.db`). Schema in `db/models.py`:
- **accounts** — phone, api_id/hash, proxy, session_file, status (`active`/`limited`/`unauthorized`), comments_today/hour counters
- **channels** — username (unique), title, has_comments flag
- **messages** — comment templates with is_active toggle
- **campaigns** — name, is_active, delay_min/max, hourly_limit, daily_limit
- **campaign_channels / campaign_accounts / campaign_messages** — junction tables (composite PKs, foreign keys)
- **logs** — per-comment execution log with status (`sent`/`error`), error text, timestamps

### Services

**`account_manager.py`** — Pyrogram client lifecycle with in-memory cache (`_clients[acc_id]`). Supports 5 account import methods: phone+code, quick (API from .env), session string, .session file upload, tdata ZIP. Handles SMS auth, 2FA password, proxy parsing (socks5/http). Dead account detection via specific Pyrogram exceptions (`AuthKeyUnregistered`, `UserDeactivated`, `UserDeactivatedBan`, `SessionRevoked`).

**`commenter.py`** — Campaign execution engine. `run_campaign()` iterates channels, picks account with lowest `comments_today` via `_pick_account()`, fetches latest post via `get_chat_history(limit=1)`, spins message text, sends as reply. Catches `FloodWait` (sleeps), `PeerFlood`/`UserBannedInChannel` (marks account `limited`), dead session errors (deletes account from DB).

**`channel_parser.py`** — 3-layer channel search: `contacts.Search()` raw API → `search_global()` → direct `get_chat()` fallback for usernames.

**`spintax.py`** — Processes `{option1|option2|option3}` syntax with nested brace support. Loops until no braces remain.

**`tdata_parser.py`** — Pure Python tdata decryption (no opentele/PyQt5). Reads TDF files, validates MD5 checksums, decrypts via AES-256-IGE, extracts user_id + dc_id + auth_key.

## Key Patterns

- **Callback data format:** `prefix_action_id` or `prefix_action_id1_id2`. Parsed via `F.data == "..."` for exact match or `F.data.startswith("prefix_")` with string splitting for ID extraction.
- **FSM states per handler:** `accounts.py` has 7 StatesGroups (AddAccount, AddQuick, AddSession, AddSessionFile, AddTdata, AuthAccount, Auth2FA, EditProxy). Other handlers have 1-2 each.
- **Admin access control:** `AccessMiddleware` in `main.py` checks both `ADMIN_IDS` (user IDs) and `ADMIN_USERNAMES`. Blocks non-admins before any handler runs.
- **Account selection strategy:** `_pick_account()` in `commenter.py` sorts by `comments_today` ascending, skips accounts exceeding hourly/daily limits.
- **Error resilience in campaigns:** Dead accounts are auto-deleted from DB. Rate-limited accounts are marked `limited`. FloodWait pauses the campaign for the required duration.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram Bot API token |
| `ADMIN_IDS` | Comma-separated Telegram user IDs with admin access |
| `ADMIN_USERNAMES` | Comma-separated Telegram usernames with admin access |
| `API_ID` | Telegram API ID from my.telegram.org (for Pyrogram) |
| `API_HASH` | Telegram API Hash from my.telegram.org (for Pyrogram) |

## Dependencies

`aiogram 3.13` (Bot API + FSM), `pyrogram 2.0` (MTProto userbot), `aiosqlite 0.20` (async SQLite), `apscheduler 3.10` (cron/interval jobs), `python-dotenv` (.env loading), `tgcrypto` (Telegram encryption for tdata).
