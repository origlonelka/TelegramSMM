import asyncio
import time
import logging
from urllib.parse import urlparse

from db.database import execute, execute_returning, fetch_one, fetch_all

logger = logging.getLogger(__name__)


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


async def check_proxy(proxy_id: int) -> dict:
    """Проверяет прокси — TCP-соединение к хосту."""
    proxy = await fetch_one("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
    if not proxy:
        return {"ok": False, "error": "Прокси не найден"}

    parsed = urlparse(proxy["url"])
    host = parsed.hostname
    port = parsed.port

    if not host or not port:
        await execute(
            "UPDATE proxies SET status = 'dead', "
            "last_checked_at = datetime('now') WHERE id = ?",
            (proxy_id,))
        return {"ok": False, "error": "Неверный формат"}

    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=10,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        writer.close()
        await writer.wait_closed()

        await execute(
            "UPDATE proxies SET status = 'alive', response_time = ?, "
            "last_checked_at = datetime('now') WHERE id = ?",
            (elapsed, proxy_id),
        )
        return {"ok": True, "response_time": elapsed}

    except Exception as e:
        await execute(
            "UPDATE proxies SET status = 'dead', "
            "last_checked_at = datetime('now') WHERE id = ?",
            (proxy_id,))
        return {"ok": False, "error": str(e)}


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
