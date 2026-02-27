import os
from pyrogram import Client
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
    except Exception as e:
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
