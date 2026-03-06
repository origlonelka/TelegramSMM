"""LikeDrom.com API client for SMM boosting services."""
import logging
import aiohttp

from db.database import fetch_one

logger = logging.getLogger(__name__)

LIKEDROM_API = "https://likedrom.com/api/"
# Ключ хранится в bot_settings (key = "likedrom_api_key")
# Fallback для первого запуска:
DEFAULT_API_KEY = "6fac0c8b8c33216d1a803300af70cf09"


async def _get_api_key() -> str:
    row = await fetch_one(
        "SELECT value FROM bot_settings WHERE key = 'likedrom_api_key'")
    return row["value"] if row else DEFAULT_API_KEY


async def _request(params: dict) -> dict | list:
    """POST-запрос к LikeDrom API."""
    params["key"] = await _get_api_key()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            LIKEDROM_API, data=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json(content_type=None)
            if isinstance(data, dict) and "error" in data:
                raise Exception(f"LikeDrom: {data['error']}")
            return data


async def get_balance() -> float:
    """Баланс аккаунта LikeDrom в рублях."""
    data = await _request({"action": "balance"})
    return float(data.get("balance", 0))


async def get_services() -> list[dict]:
    """Список всех доступных сервисов."""
    data = await _request({"action": "services"})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # API может возвращать {id: {service_info}, ...}
        result = []
        for sid, info in data.items():
            if isinstance(info, dict):
                info["service"] = int(sid)
                result.append(info)
        return result
    return []


async def create_order(service_id: int, link: str, quantity: int,
                       **kwargs) -> int:
    """Создаёт заказ. Возвращает order_id."""
    params = {
        "action": "add",
        "service": str(service_id),
        "link": link,
        "quantity": str(quantity),
    }
    params.update(kwargs)
    data = await _request(params)
    return int(data["order"])


async def check_order(order_id: int) -> dict:
    """Статус заказа. Возвращает {status, charge, start_count, remains, ...}."""
    data = await _request({
        "action": "status",
        "order": str(order_id),
    })
    return data


async def cancel_order(order_id: int) -> bool:
    """Отменяет заказ."""
    try:
        await _request({"action": "cancel", "order": str(order_id)})
        return True
    except Exception as e:
        logger.warning(f"LikeDrom cancel #{order_id} failed: {e}")
        return False
