import asyncio
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from core.config import SESSIONS_DIR

logger = logging.getLogger(__name__)

os.makedirs(SESSIONS_DIR, exist_ok=True)

# Хранилище клиентов в памяти
_clients: dict[int, Client] = {}


def _get_session_path(acc_id: int) -> str:
    return os.path.join(SESSIONS_DIR, f"account_{acc_id}")


def _parse_proxy(proxy_str: str | None) -> dict | None:
    """Парсит строку прокси в dict для Pyrogram.

    Форматы:
      socks5://user:pass@host:port
      http://host:port
      socks5://host:port
    """
    if not proxy_str:
        return None

    proxy_str = proxy_str.strip()
    scheme = "socks5"
    rest = proxy_str

    if "://" in proxy_str:
        scheme, rest = proxy_str.split("://", 1)

    username = None
    password = None

    if "@" in rest:
        creds, rest = rest.rsplit("@", 1)
        if ":" in creds:
            username, password = creds.split(":", 1)
        else:
            username = creds

    if ":" in rest:
        hostname, port_str = rest.rsplit(":", 1)
        port = int(port_str)
    else:
        hostname = rest
        port = 1080

    return {
        "scheme": scheme,
        "hostname": hostname,
        "port": port,
        "username": username,
        "password": password,
    }


def get_client(acc) -> Client:
    acc_id = acc["id"]
    if acc_id not in _clients:
        proxy = _parse_proxy(acc["proxy"])
        _clients[acc_id] = Client(
            name=_get_session_path(acc_id),
            api_id=acc["api_id"],
            api_hash=acc["api_hash"],
            phone_number=acc["phone"],
            proxy=proxy,
        )
    return _clients[acc_id]


async def send_code(acc) -> dict:
    try:
        client = get_client(acc)
        await client.connect()
        sent_code = await client.send_code(acc["phone"])
        return {"ok": True, "phone_code_hash": sent_code.phone_code_hash}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def sign_in(acc, code: str, phone_code_hash: str) -> dict:
    try:
        client = get_client(acc)
        await client.sign_in(acc["phone"], phone_code_hash, code)
        await client.disconnect()
        return {"ok": True}
    except SessionPasswordNeeded:
        return {"ok": False, "need_2fa": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def sign_in_2fa(acc, password: str) -> dict:
    """Завершает авторизацию с двухфакторным паролем."""
    try:
        client = get_client(acc)
        await client.check_password(password)
        await client.disconnect()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def import_session_string(session_string: str, api_id: int, api_hash: str,
                                 acc_id: int, proxy_str: str | None = None) -> dict:
    """Импортирует аккаунт из session string."""
    try:
        proxy = _parse_proxy(proxy_str)
        client = Client(
            name=_get_session_path(acc_id),
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            proxy=proxy,
        )
        await client.start()
        me = await client.get_me()
        phone = f"+{me.phone_number}" if me.phone_number else "unknown"
        await client.stop()
        return {"ok": True, "phone": phone}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def import_session_file(file_path: str, api_id: int, api_hash: str,
                               acc_id: int, proxy_str: str | None = None) -> dict:
    """Импортирует аккаунт из .session файла."""
    try:
        dest = _get_session_path(acc_id) + ".session"
        shutil.copy2(file_path, dest)

        proxy = _parse_proxy(proxy_str)
        client = Client(
            name=_get_session_path(acc_id),
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy,
        )
        await client.start()
        me = await client.get_me()
        phone = f"+{me.phone_number}" if me.phone_number else "unknown"
        await client.stop()
        return {"ok": True, "phone": phone}
    except Exception as e:
        # Удаляем скопированный файл если не удалось
        dest = _get_session_path(acc_id) + ".session"
        if os.path.exists(dest):
            os.remove(dest)
        return {"ok": False, "error": str(e)}


def _find_tdata_dir(base_path: str) -> str | None:
    """Ищет папку tdata внутри извлечённого архива."""
    # Может быть напрямую base_path/tdata или base_path/*/tdata
    for root, dirs, _files in os.walk(base_path):
        if "tdata" in dirs:
            return os.path.join(root, "tdata")
    # Или сама base_path и есть tdata
    if os.path.basename(base_path) == "tdata":
        return base_path
    return None


def _tdata_to_session(tdata_path: str, session_path: str, api_id: int) -> None:
    """Конвертирует tdata в Pyrogram .session файл (SQLite)."""
    from services.tdata_parser import read_tdata

    tdata_result = read_tdata(tdata_path)
    auth_key = tdata_result["auth_key"]  # 256 bytes
    dc_id = tdata_result["dc_id"]
    user_id = tdata_result["user_id"]

    session_file = f"{session_path}.session"
    conn = sqlite3.connect(session_file)
    try:
        conn.executescript("""
            CREATE TABLE sessions (
                dc_id     INTEGER PRIMARY KEY,
                api_id    INTEGER,
                test_mode INTEGER,
                auth_key  BLOB,
                date      INTEGER NOT NULL,
                user_id   INTEGER,
                is_bot    INTEGER
            );
            CREATE TABLE peers (
                id             INTEGER PRIMARY KEY,
                access_hash    INTEGER,
                type           INTEGER NOT NULL,
                username       TEXT,
                phone_number   TEXT,
                last_update_on INTEGER NOT NULL DEFAULT (CAST(STRFTIME('%s', 'now') AS INTEGER))
            );
            CREATE TABLE version (
                number INTEGER PRIMARY KEY
            );
            CREATE INDEX idx_peers_id ON peers (id);
            CREATE INDEX idx_peers_username ON peers (username);
            CREATE INDEX idx_peers_phone_number ON peers (phone_number);
        """)
        conn.execute("INSERT INTO version VALUES (?)", (3,))
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, 0, ?, 0, ?, 0)",
            (dc_id, api_id, auth_key, user_id),
        )
        conn.commit()
    finally:
        conn.close()


async def import_tdata(zip_path: str, api_id: int, api_hash: str,
                       acc_id: int, proxy_str: str | None = None) -> dict:
    """Импортирует аккаунт из ZIP-архива с tdata."""
    tmp_dir = None
    try:
        # 1. Распаковываем ZIP
        tmp_dir = tempfile.mkdtemp(prefix="tdata_")
        logger.info(f"[tdata] Шаг 1: распаковка ZIP в {tmp_dir}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        # Фиксим права на файлы после распаковки
        for root, dirs, files in os.walk(tmp_dir):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for f in files:
                os.chmod(os.path.join(root, f), 0o644)

        # 2. Ищем папку tdata
        tdata_path = _find_tdata_dir(tmp_dir)
        if not tdata_path:
            return {"ok": False, "error": "Папка tdata не найдена в архиве"}
        logger.info(f"[tdata] Шаг 2: найдена папка tdata: {tdata_path}")

        # Логируем содержимое папки tdata
        tdata_files = os.listdir(tdata_path)
        logger.info(f"[tdata] Файлы в tdata: {tdata_files}")

        # 3. Конвертируем в Pyrogram session
        logger.info("[tdata] Шаг 3: конвертация tdata → session")
        session_path = _get_session_path(acc_id)
        _tdata_to_session(tdata_path, session_path, api_id)
        logger.info("[tdata] Шаг 3: конвертация успешна")

        # 4. Подключаемся Pyrogram'ом для проверки
        logger.info("[tdata] Шаг 4: проверка сессии через Pyrogram")
        proxy = _parse_proxy(proxy_str)
        client = Client(
            name=session_path,
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy,
        )
        await client.start()
        me = await client.get_me()
        phone = f"+{me.phone_number}" if me.phone_number else "unknown"
        await client.stop()

        logger.info(f"[tdata] Импорт завершён для #{acc_id}: {phone}")
        return {"ok": True, "phone": phone}

    except zipfile.BadZipFile:
        return {"ok": False, "error": "Файл не является ZIP-архивом"}
    except Exception as e:
        # Удаляем session файл если создался
        session_file = _get_session_path(acc_id) + ".session"
        if os.path.exists(session_file):
            os.remove(session_file)
        logger.error(f"[tdata] Ошибка на этапе импорта: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
    finally:
        # Чистим временную папку
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


_DEAD_ERRORS = (
    "AUTH_KEY_UNREGISTERED", "USER_DEACTIVATED", "USER_DEACTIVATED_BAN",
    "SESSION_REVOKED", "SESSION_EXPIRED", "AUTH_KEY_INVALID",
)


def _is_dead_error(error_str: str) -> bool:
    """Проверяет, является ли ошибка признаком мёртвого аккаунта."""
    upper = error_str.upper()
    return any(code in upper for code in _DEAD_ERRORS)


async def check_account(acc, timeout: int = 30) -> dict:
    """Проверяет валидность сессии аккаунта.

    Возвращает:
        {"ok": True, "phone": ...} — аккаунт жив
        {"ok": False, "dead": True, "error": ...} — аккаунт мёртв (удалять)
        {"ok": False, "dead": False, "error": ...} — ошибка сети/таймаут (не удалять)
    """
    acc_id = acc["id"]

    # 1. Проверяем наличие файла сессии
    session_file = _get_session_path(acc_id) + ".session"
    if not os.path.exists(session_file):
        return {"ok": False, "dead": True, "error": "Файл сессии не найден"}

    async def _do_check():
        # Используем connect() вместо start() чтобы не попасть
        # в интерактивную авторизацию (input() блокирует event loop)
        proxy = _parse_proxy(acc["proxy"])
        client = Client(
            name=_get_session_path(acc_id),
            api_id=acc["api_id"],
            api_hash=acc["api_hash"],
            proxy=proxy,
        )
        try:
            await client.connect()
            me = await client.get_me()
            phone = f"+{me.phone_number}" if me.phone_number else None
            await client.disconnect()
            return {"ok": True, "phone": phone}
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise

    # Убираем старый клиент из кеша — проверка использует свой
    if acc_id in _clients:
        del _clients[acc_id]

    task = asyncio.create_task(_do_check())
    done, _ = await asyncio.wait({task}, timeout=timeout)

    if done:
        try:
            return task.result()
        except Exception as e:
            err = str(e)
            dead = _is_dead_error(err)
            return {"ok": False, "dead": dead, "error": err}
    else:
        # Таймаут — бросаем задачу, не ждём отмены
        task.cancel()
        return {
            "ok": False,
            "dead": False,
            "error": f"Таймаут ({timeout} сек) — нет связи с Telegram. Проверьте прокси.",
        }


async def ensure_connected(acc) -> Client:
    client = get_client(acc)
    if not client.is_connected:
        await client.start()
    return client


async def disconnect(acc_id: int):
    if acc_id in _clients:
        client = _clients[acc_id]
        if client.is_connected:
            await client.stop()
        del _clients[acc_id]
