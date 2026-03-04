import asyncio
import struct
import time
import logging
from urllib.parse import urlparse

from db.database import execute, execute_returning, fetch_one, fetch_all

logger = logging.getLogger(__name__)

# Telegram DC2 for connectivity test
_TG_DC2_HOST = "149.154.167.50"
_TG_DC2_PORT = 443


def parse_proxy_line(line: str) -> dict | None:
    """Парсит строку прокси в различных форматах.

    Поддерживаемые форматы:
      socks5://user:pass@host:port
      http://host:port
      host:port:user:pass  (по умолчанию socks5)
      host:port            (по умолчанию socks5)
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Формат с протоколом: protocol://...
    if "://" in line:
        parsed = urlparse(line)
        if not parsed.hostname or not parsed.port:
            return None
        return {
            "url": line,
            "type": parsed.scheme or "socks5",
        }

    # Формат host:port
    parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        if not port.isdigit():
            return None
        url = f"socks5://{host}:{port}"
        return {"url": url, "type": "socks5"}

    # Формат host:port:user:pass
    if len(parts) == 4:
        host, port, user, pwd = parts
        if not port.isdigit():
            return None
        url = f"socks5://{user}:{pwd}@{host}:{port}"
        return {"url": url, "type": "socks5"}

    # Формат user:pass@host:port (без протокола)
    if "@" in line:
        url = f"socks5://{line}"
        parsed = urlparse(url)
        if parsed.hostname and parsed.port:
            return {"url": url, "type": "socks5"}

    return None


async def import_proxies(text: str) -> dict:
    """Импорт прокси из текста (по одной на строку)."""
    lines = text.strip().split("\n")
    added = 0
    skipped = 0
    errors = 0

    for line in lines:
        parsed = parse_proxy_line(line)
        if not parsed:
            if line.strip() and not line.strip().startswith("#"):
                errors += 1
            continue

        existing = await fetch_one(
            "SELECT id FROM proxies WHERE url = ?", (parsed["url"],))
        if existing:
            skipped += 1
            continue

        await execute_returning(
            "INSERT INTO proxies (url, type) VALUES (?, ?)",
            (parsed["url"], parsed["type"]),
        )
        added += 1

    return {"added": added, "skipped": skipped, "errors": errors}


async def _socks5_handshake(reader, writer, username=None, password=None):
    """Perform SOCKS5 handshake and request CONNECT to Telegram DC2."""
    # Greeting: version=5, 1 method (0x00=no auth or 0x02=user/pass)
    if username and password:
        writer.write(b"\x05\x02\x00\x02")  # offer no-auth and user/pass
    else:
        writer.write(b"\x05\x01\x00")  # offer no-auth only
    await writer.drain()

    resp = await reader.readexactly(2)
    if resp[0] != 0x05:
        raise ValueError("Not a SOCKS5 proxy")

    chosen_method = resp[1]
    if chosen_method == 0x02:
        # Username/password auth (RFC 1929)
        if not username or not password:
            raise ValueError("Proxy requires auth but no credentials provided")
        user_bytes = username.encode()
        pass_bytes = password.encode()
        writer.write(
            b"\x01"
            + bytes([len(user_bytes)]) + user_bytes
            + bytes([len(pass_bytes)]) + pass_bytes
        )
        await writer.drain()
        auth_resp = await reader.readexactly(2)
        if auth_resp[1] != 0x00:
            raise PermissionError("SOCKS5 auth failed")
    elif chosen_method == 0xFF:
        raise PermissionError("SOCKS5 no acceptable auth methods")

    # CONNECT request to Telegram DC2
    ip_bytes = bytes(int(x) for x in _TG_DC2_HOST.split("."))
    port_bytes = struct.pack("!H", _TG_DC2_PORT)
    writer.write(b"\x05\x01\x00\x01" + ip_bytes + port_bytes)
    await writer.drain()

    connect_resp = await reader.readexactly(4)
    if connect_resp[1] != 0x00:
        raise ConnectionError(f"SOCKS5 CONNECT failed: status {connect_resp[1]}")

    # Read remaining address bytes
    atype = connect_resp[3]
    if atype == 0x01:  # IPv4
        await reader.readexactly(4 + 2)
    elif atype == 0x03:  # Domain
        length = (await reader.readexactly(1))[0]
        await reader.readexactly(length + 2)
    elif atype == 0x04:  # IPv6
        await reader.readexactly(16 + 2)


async def _http_connect_handshake(reader, writer, username=None, password=None):
    """Perform HTTP CONNECT to Telegram DC2 through HTTP proxy."""
    connect_line = f"CONNECT {_TG_DC2_HOST}:{_TG_DC2_PORT} HTTP/1.1\r\nHost: {_TG_DC2_HOST}:{_TG_DC2_PORT}\r\n"
    if username and password:
        import base64
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        connect_line += f"Proxy-Authorization: Basic {creds}\r\n"
    connect_line += "\r\n"
    writer.write(connect_line.encode())
    await writer.drain()

    # Read status line
    status_line = await reader.readline()
    status_str = status_line.decode(errors="replace")
    if " 200 " not in status_str:
        if " 407 " in status_str:
            raise PermissionError("HTTP proxy auth failed (407)")
        raise ConnectionError(f"HTTP CONNECT failed: {status_str.strip()}")

    # Read remaining headers until empty line
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break


async def check_proxy(proxy_id: int) -> dict:
    """Проверяет прокси — SOCKS5/HTTP handshake + подключение к Telegram DC."""
    proxy = await fetch_one("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
    if not proxy:
        return {"ok": False, "error": "Прокси не найден"}

    parsed = urlparse(proxy["url"])
    host = parsed.hostname
    port = parsed.port
    scheme = (parsed.scheme or "socks5").lower()
    username = parsed.username
    password = parsed.password

    if not host or not port:
        await execute(
            "UPDATE proxies SET status = 'dead', last_error = 'Invalid format', "
            "last_checked_at = datetime('now') WHERE id = ?",
            (proxy_id,))
        return {"ok": False, "error": "Неверный формат"}

    start_time = time.monotonic()
    status = "dead"
    error_msg = None

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10)

        try:
            if scheme in ("socks5", "socks5h"):
                await asyncio.wait_for(
                    _socks5_handshake(reader, writer, username, password),
                    timeout=10)
            elif scheme in ("http", "https"):
                await asyncio.wait_for(
                    _http_connect_handshake(reader, writer, username, password),
                    timeout=10)
            else:
                # Fallback: try SOCKS5
                await asyncio.wait_for(
                    _socks5_handshake(reader, writer, username, password),
                    timeout=10)

            status = "alive"
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    except PermissionError as e:
        status = "auth_failed"
        error_msg = str(e)
    except asyncio.TimeoutError:
        status = "timeout"
        error_msg = "Connection/handshake timeout"
    except Exception as e:
        status = "dead"
        error_msg = str(e)

    elapsed = int((time.monotonic() - start_time) * 1000)

    await execute(
        "UPDATE proxies SET status = ?, response_time = ?, latency_ms = ?, "
        "last_error = ?, last_checked_at = datetime('now') WHERE id = ?",
        (status, elapsed if status == "alive" else None,
         elapsed, error_msg, proxy_id))

    if status == "alive":
        return {"ok": True, "response_time": elapsed, "status": status}
    return {"ok": False, "error": error_msg or status, "status": status}


async def check_all_proxies() -> dict:
    """Проверяет все прокси в пуле (параллельно, батчами по 20)."""
    proxies = await fetch_all("SELECT id FROM proxies ORDER BY id")
    alive = 0
    dead = 0

    batch_size = 20
    for i in range(0, len(proxies), batch_size):
        batch = proxies[i:i + batch_size]
        results = await asyncio.gather(
            *[check_proxy(p["id"]) for p in batch],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, dict) and r.get("ok"):
                alive += 1
            else:
                dead += 1

    return {"total": len(proxies), "alive": alive, "dead": dead}


async def assign_proxy_to_account(acc_id: int) -> dict:
    """Назначает свободный живой прокси аккаунту."""
    proxy = await fetch_one(
        "SELECT * FROM proxies WHERE status = 'alive' AND account_id IS NULL "
        "ORDER BY response_time ASC LIMIT 1")

    if not proxy:
        return {"ok": False, "error": "Нет свободных живых прокси"}

    await execute(
        "UPDATE proxies SET account_id = ? WHERE id = ?",
        (acc_id, proxy["id"]))
    await execute(
        "UPDATE accounts SET proxy = ? WHERE id = ?",
        (proxy["url"], acc_id))

    try:
        from services.account_manager import disconnect
        await disconnect(acc_id)
    except Exception:
        pass

    return {"ok": True, "proxy_url": proxy["url"]}


async def auto_assign_all() -> dict:
    """Назначает прокси всем аккаунтам без прокси."""
    accounts = await fetch_all(
        "SELECT id FROM accounts WHERE "
        "(proxy IS NULL OR proxy = '') AND status = 'active'")

    assigned = 0
    for acc in accounts:
        result = await assign_proxy_to_account(acc["id"])
        if result["ok"]:
            assigned += 1
        else:
            break  # нет свободных прокси

    return {
        "assigned": assigned,
        "remaining": len(accounts) - assigned,
        "total": len(accounts),
    }


async def rotate_dead_proxies() -> dict:
    """Заменяет мёртвые прокси на живые для аккаунтов."""
    dead_assigned = await fetch_all(
        "SELECT p.id as proxy_id, p.account_id FROM proxies p "
        "WHERE p.status = 'dead' AND p.account_id IS NOT NULL")

    rotated = 0
    failed = 0

    for dp in dead_assigned:
        acc_id = dp["account_id"]
        # Освобождаем мёртвый прокси
        await execute(
            "UPDATE proxies SET account_id = NULL WHERE id = ?",
            (dp["proxy_id"],))

        result = await assign_proxy_to_account(acc_id)
        if result["ok"]:
            rotated += 1
        else:
            await execute(
                "UPDATE accounts SET proxy = NULL WHERE id = ?", (acc_id,))
            failed += 1

    return {"rotated": rotated, "failed": failed}


async def free_proxy(proxy_id: int):
    """Освобождает прокси от аккаунта."""
    proxy = await fetch_one("SELECT account_id, url FROM proxies WHERE id = ?", (proxy_id,))
    if not proxy:
        return

    # Очищаем по account_id (прямая связь)
    if proxy["account_id"]:
        await execute(
            "UPDATE accounts SET proxy = NULL WHERE id = ?",
            (proxy["account_id"],))
        try:
            from services.account_manager import disconnect
            await disconnect(proxy["account_id"])
        except Exception:
            pass

    # Очищаем по URL (на случай рассинхрона account_id)
    if proxy["url"]:
        affected = await fetch_all(
            "SELECT id FROM accounts WHERE proxy = ?", (proxy["url"],))
        if affected:
            await execute(
                "UPDATE accounts SET proxy = NULL WHERE proxy = ?",
                (proxy["url"],))
            from services.account_manager import disconnect
            for acc in affected:
                try:
                    await disconnect(acc["id"])
                except Exception:
                    pass

    await execute(
        "UPDATE proxies SET account_id = NULL WHERE id = ?", (proxy_id,))


async def delete_proxy(proxy_id: int):
    """Удаляет прокси из пула, освобождая аккаунт."""
    await free_proxy(proxy_id)
    await execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))


async def delete_dead_proxies() -> int:
    """Удаляет все мёртвые прокси."""
    dead = await fetch_all(
        "SELECT id FROM proxies WHERE status = 'dead'")
    for p in dead:
        await delete_proxy(p["id"])
    return len(dead)


async def get_pool_stats() -> dict:
    """Статистика пула прокси."""
    total = await fetch_one("SELECT COUNT(*) as cnt FROM proxies")
    alive = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE status = 'alive'")
    dead = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE status = 'dead'")
    unchecked = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE status = 'unchecked'")
    assigned = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies WHERE account_id IS NOT NULL")
    free = await fetch_one(
        "SELECT COUNT(*) as cnt FROM proxies "
        "WHERE account_id IS NULL AND status = 'alive'")

    return {
        "total": total["cnt"],
        "alive": alive["cnt"],
        "dead": dead["cnt"],
        "unchecked": unchecked["cnt"],
        "assigned": assigned["cnt"],
        "free": free["cnt"],
    }


async def clear_all_account_proxies() -> int:
    """Снимает прокси со всех аккаунтов."""
    accounts = await fetch_all(
        "SELECT id FROM accounts WHERE proxy IS NOT NULL AND proxy != ''")
    for acc in accounts:
        try:
            from services.account_manager import disconnect
            await disconnect(acc["id"])
        except Exception:
            pass
    await execute("UPDATE accounts SET proxy = NULL WHERE proxy IS NOT NULL")
    await execute("UPDATE proxies SET account_id = NULL WHERE account_id IS NOT NULL")
    return len(accounts)
