import asyncio
import json
import os
import logging
import aiohttp

from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, FloodWait, PhoneNumberBanned,
    PhoneNumberInvalid,
)

from db.database import execute, execute_returning, fetch_one, fetch_all
from core.config import API_ID, API_HASH, SESSIONS_DIR
from services.account_manager import _parse_proxy
from services.spintax import spin

logger = logging.getLogger(__name__)

os.makedirs(SESSIONS_DIR, exist_ok=True)

SMS_ACTIVATE_URL = "https://hero-sms.com/stubs/handler_api.php"

COUNTRIES = {
    0: "🇷🇺 Россия",
    1: "🇺🇦 Украина",
    2: "🇰🇿 Казахстан",
    6: "🇮🇩 Индонезия",
    12: "🇺🇸 США",
    16: "🇬🇧 Великобритания",
    22: "🇮🇳 Индия",
    56: "🇹🇷 Турция",
    175: "🇧🇷 Бразилия",
    187: "🇳🇬 Нигерия",
}

DEFAULT_NAMES = "{Алексей|Дмитрий|Иван|Сергей|Андрей|Михаил|Максим|Артём|Данил|Никита}"


# --- Настройки ---

async def get_setting(key: str) -> str | None:
    row = await fetch_one("SELECT value FROM bot_settings WHERE key = ?", (key,))
    return row["value"] if row else None


async def set_setting(key: str, value: str):
    existing = await fetch_one("SELECT key FROM bot_settings WHERE key = ?", (key,))
    if existing:
        await execute("UPDATE bot_settings SET value = ? WHERE key = ?", (value, key))
    else:
        await execute("INSERT INTO bot_settings (key, value) VALUES (?, ?)", (key, value))


# --- HeroSMS API ---

async def _sms_request(params: dict) -> str:
    api_key = await get_setting("sms_api_key")
    if not api_key:
        raise Exception("SMS API ключ не настроен")
    params["api_key"] = api_key
    async with aiohttp.ClientSession() as session:
        async with session.get(SMS_ACTIVATE_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            return await resp.text()


async def get_balance() -> float:
    text = await _sms_request({"action": "getBalance"})
    if text.startswith("ACCESS_BALANCE:"):
        return float(text.split(":")[1])
    raise Exception(f"Ошибка: {text}")


async def _get_min_price(country: int = 0) -> float | None:
    """Получает минимальную цену на номер Telegram в указанной стране."""
    text = await _sms_request({
        "action": "getPrices",
        "service": "tg",
        "country": str(country),
    })
    try:
        data = json.loads(text)
        prices = []

        def extract_prices(obj):
            if isinstance(obj, dict):
                if "cost" in obj:
                    prices.append(float(obj["cost"]))
                else:
                    for v in obj.values():
                        extract_prices(v)

        extract_prices(data)
        return min(prices) if prices else None
    except Exception:
        return None


async def get_all_min_prices() -> dict[int, float]:
    """Получает минимальные цены для всех стран параллельно."""
    import asyncio

    async def _fetch(code: int) -> tuple[int, float | None]:
        price = await _get_min_price(code)
        return code, price

    results = await asyncio.gather(
        *[_fetch(code) for code in COUNTRIES], return_exceptions=True
    )
    prices = {}
    for r in results:
        if isinstance(r, tuple) and r[1] is not None:
            prices[r[0]] = r[1]
    return prices


async def _buy_number(country: int = 0) -> dict:
    min_price = await _get_min_price(country)

    params = {
        "action": "getNumber",
        "service": "tg",
        "country": str(country),
    }
    if min_price is not None:
        params["maxPrice"] = str(min_price)

    text = await _sms_request(params)
    if text.startswith("ACCESS_NUMBER:"):
        parts = text.split(":")
        return {"activation_id": parts[1], "phone": "+" + parts[2]}
    raise Exception(text)


async def _set_activation_status(activation_id: str, status: int) -> str:
    return await _sms_request({
        "action": "setStatus",
        "id": activation_id,
        "status": str(status),
    })


async def _wait_for_code(activation_id: str, timeout: int = 150) -> str | None:
    """Ждёт SMS-код от сервиса. Polling каждые 3 секунды."""
    api_key = await get_setting("sms_api_key")
    async with aiohttp.ClientSession() as session:
        for _ in range(timeout // 3):
            async with session.get(
                SMS_ACTIVATE_URL,
                params={
                    "api_key": api_key,
                    "action": "getStatus",
                    "id": activation_id,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                text = await resp.text()
                if text.startswith("STATUS_OK:"):
                    return text.split(":")[1]
                if text == "STATUS_CANCEL":
                    return None
            await asyncio.sleep(3)
    return None


# --- Регистрация ---

async def register_one_account(country: int = 0,
                                progress_callback=None) -> dict:
    """Полный цикл авторегистрации одного аккаунта.

    progress_callback(text) — опциональный коллбэк для обновления прогресса.
    """
    if not API_ID or not API_HASH:
        return {"ok": False, "error": "API_ID и API_HASH не заданы в .env"}

    api_key = await get_setting("sms_api_key")
    if not api_key:
        return {"ok": False, "error": "SMS API ключ не настроен"}

    # Берём прокси из пула (свободный живой)
    proxy_row = await fetch_one(
        "SELECT * FROM proxies WHERE status = 'alive' AND account_id IS NULL "
        "ORDER BY response_time ASC LIMIT 1")
    proxy_url = proxy_row["url"] if proxy_row else None
    proxy_dict = _parse_proxy(proxy_url)

    # 1. Покупаем номер
    if progress_callback:
        await progress_callback("📱 Покупаю номер...")

    try:
        number_info = await _buy_number(country)
    except Exception as e:
        return {"ok": False, "error": f"Покупка номера: {e}"}

    phone = number_info["phone"]
    activation_id = number_info["activation_id"]

    if progress_callback:
        await progress_callback(f"📱 {phone}\n📡 Отправляю код...")

    # 2. Создаём запись в БД для получения ID
    acc_id = await execute_returning(
        "INSERT INTO accounts (phone, api_id, api_hash, proxy, status) "
        "VALUES (?, ?, ?, ?, 'registering')",
        (phone, API_ID, API_HASH, proxy_url),
    )

    session_path = os.path.join(SESSIONS_DIR, f"account_{acc_id}")
    client = Client(
        name=session_path,
        api_id=API_ID,
        api_hash=API_HASH,
        proxy=proxy_dict,
    )

    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        phone_code_hash = sent_code.phone_code_hash

        # 3. Сообщаем SMS-сервису: готовы принять SMS
        await _set_activation_status(activation_id, 1)

        if progress_callback:
            await progress_callback(f"📱 {phone}\n⏳ Жду SMS-код...")

        # 4. Ждём код
        code = await _wait_for_code(activation_id, timeout=150)

        if not code:
            await _set_activation_status(activation_id, 8)  # отмена
            try:
                await client.disconnect()
            except Exception:
                pass
            await _cleanup_account(acc_id, session_path)
            return {"ok": False, "error": f"SMS не пришёл для {phone}"}

        if progress_callback:
            await progress_callback(f"📱 {phone}\n🔑 Код получен, регистрирую...")

        # 5. Входим / регистрируемся
        is_new = False
        try:
            await client.sign_in(phone, phone_code_hash, code)
        except Exception as e:
            err_name = type(e).__name__
            if "PhoneNumberUnoccupied" in err_name or "PHONE_NUMBER_UNOCCUPIED" in str(e).upper():
                first_name = spin(DEFAULT_NAMES)
                await client.sign_up(phone, phone_code_hash, first_name)
                is_new = True
            elif isinstance(e, SessionPasswordNeeded):
                # Аккаунт с 2FA — не можем авторег
                await _set_activation_status(activation_id, 6)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await _cleanup_account(acc_id, session_path)
                return {"ok": False, "error": f"{phone} — требуется 2FA пароль"}
            else:
                raise

        await client.disconnect()

        # 6. Успех — обновляем БД
        await execute(
            "UPDATE accounts SET status = 'active', session_file = ? WHERE id = ?",
            (session_path + ".session", acc_id),
        )

        # Привязываем прокси
        if proxy_row:
            await execute(
                "UPDATE proxies SET account_id = ? WHERE id = ?",
                (acc_id, proxy_row["id"]))

        # Завершаем активацию на SMS-сервисе
        await _set_activation_status(activation_id, 6)

        logger.info(
            f"Авторег: {phone} (#{acc_id}) — "
            f"{'новый аккаунт' if is_new else 'существующий'}")

        return {
            "ok": True,
            "phone": phone,
            "acc_id": acc_id,
            "is_new": is_new,
        }

    except FloodWait as e:
        await _set_activation_status(activation_id, 8)
        try:
            await client.disconnect()
        except Exception:
            pass
        await _cleanup_account(acc_id, session_path)
        return {"ok": False, "error": f"FloodWait: подождите {e.value} сек"}

    except PhoneNumberBanned:
        await _set_activation_status(activation_id, 8)
        try:
            await client.disconnect()
        except Exception:
            pass
        await _cleanup_account(acc_id, session_path)
        return {"ok": False, "error": f"{phone} забанен в Telegram"}

    except PhoneNumberInvalid:
        await _set_activation_status(activation_id, 8)
        try:
            await client.disconnect()
        except Exception:
            pass
        await _cleanup_account(acc_id, session_path)
        return {"ok": False, "error": f"{phone} — невалидный номер"}

    except Exception as e:
        await _set_activation_status(activation_id, 8)
        try:
            await client.disconnect()
        except Exception:
            pass
        await _cleanup_account(acc_id, session_path)
        logger.error(f"Авторег ошибка: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def _cleanup_account(acc_id: int, session_path: str):
    """Удаляет аккаунт и session файл при неудаче."""
    from db.database import delete_account
    await delete_account(acc_id)
    for ext in (".session", ".session-journal", ".session-wal", ".session-shm"):
        f = session_path + ext
        if os.path.exists(f):
            os.remove(f)
