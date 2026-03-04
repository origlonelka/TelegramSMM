import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# ADMIN_IDS kept for backward compat — maps to SUPERADMIN_IDS
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
SUPERADMIN_IDS = [int(x) for x in os.getenv("SUPERADMIN_IDS", "").split(",") if x.strip()]
# Merge: anyone in ADMIN_IDS is also a superadmin
SUPERADMIN_IDS = list(set(SUPERADMIN_IDS + ADMIN_IDS))
API_ID = int(os.getenv("API_ID") or "0")
API_HASH = os.getenv("API_HASH") or ""

DB_PATH = "data.db"
SESSIONS_DIR = "sessions"
