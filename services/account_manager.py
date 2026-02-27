import os
import shutil
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from core.config import SESSIONS_DIR

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
        proxy = _parse_proxy(acc.get("proxy"))
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
        _clients[acc_id] = client
        return {"ok": True, "phone": phone}
    except Exception as e:
        # Удаляем скопированный файл если не удалось
        dest = _get_session_path(acc_id) + ".session"
        if os.path.exists(dest):
            os.remove(dest)
        return {"ok": False, "error": str(e)}


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
