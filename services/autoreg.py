import asyncio
import json
import os
import logging
import aiohttp

from pyrogram import Client
from pyrogram.enums import SentCodeType
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

FIVESIM_BASE = "https://5sim.net/v1"

COUNTRIES = {
    "russia": "🇷🇺 Россия",
    "ukraine": "🇺🇦 Украина",
    "kazakhstan": "🇰🇿 Казахстан",
    "indonesia": "🇮🇩 Индонезия",
    "usa": "🇺🇸 США",
    "england": "🇬🇧 Великобритания",
    "india": "🇮🇳 Индия",
    "turkey": "🇹🇷 Турция",
    "brazil": "🇧🇷 Бразилия",
    "nigeria": "🇳🇬 Нигерия",
    "philippines": "🇵🇭 Филиппины",
    "mexico": "🇲🇽 Мексика",
    "colombia": "🇨🇴 Колумбия",
    "bangladesh": "🇧🇩 Бангладеш",
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


# --- 5sim.net API ---

async def _fivesim_request(method: str, path: str,
                           params: dict = None) -> dict | list:
    """HTTP запрос к 5sim.net API. Возвращает JSON."""
    api_key = await get_setting("sms_api_key")
    if not api_key:
        raise Exception("SMS API ключ не настроен")
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    url = f"{FIVESIM_BASE}{path}"
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers, params=params,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"5sim {resp.status}: {text}")
                return await resp.json()
        else:
            async with session.post(url, headers=headers, params=params,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"5sim {resp.status}: {text}")
                return await resp.json()


async def get_balance() -> float:
    """Возвращает баланс в рублях."""
    data = await _fivesim_request("GET", "/user/profile")
    return float(data.get("balance", 0))


async def _get_min_price(country: str = "russia") -> float | None:
    """Получает минимальную цену на номер Telegram в указанной стране."""
    try:
        api_key = await get_setting("sms_api_key")
        if not api_key:
            return None
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        url = f"{FIVESIM_BASE}/guest/prices?product=telegram&country={country}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                # Response: {country: {operator: {product: {cost, count}}}}
                prices = []
                if country in data:
                    for operator, products in data[country].items():
                        if "telegram" in products:
                            info = products["telegram"]
                            count = int(info.get("count", 0))
                            if count > 0:
                                prices.append(float(info["cost"]))
                return min(prices) if prices else None
    except Exception:
        return None


async def get_all_min_prices() -> dict[str, float]:
    """Получает минимальные цены для всех стран параллельно."""
    async def _fetch(code: str) -> tuple[str, float | None]:
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


async def _buy_number(country: str = "russia") -> dict:
    """Покупает номер для Telegram. Возвращает {order_id, phone}."""
    data = await _fivesim_request(
        "GET", f"/user/buy/activation/{country}/any/telegram")
    order_id = data["id"]
    phone = data["phone"]
    # 5sim возвращает номер уже с +
    if not phone.startswith("+"):
        phone = "+" + phone
    logger.info(f"5sim: куплен номер {phone} (order #{order_id})")
    return {"activation_id": str(order_id), "phone": phone}


async def _cancel_order(order_id: str):
    """Отменяет заказ (возврат средств)."""
    try:
        await _fivesim_request("GET", f"/user/cancel/{order_id}")
        logger.info(f"5sim: заказ #{order_id} отменён")
    except Exception as e:
        logger.warning(f"5sim: ошибка отмены #{order_id}: {e}")


async def _finish_order(order_id: str):
    """Завершает заказ (SMS получен, всё ок)."""
    try:
        await _fivesim_request("GET", f"/user/finish/{order_id}")
        logger.info(f"5sim: заказ #{order_id} завершён")
    except Exception as e:
        logger.warning(f"5sim: ошибка завершения #{order_id}: {e}")


async def _ban_order(order_id: str):
    """Баним номер (номер оказался плохим)."""
    try:
        await _fivesim_request("GET", f"/user/ban/{order_id}")
        logger.info(f"5sim: номер #{order_id} забанен")
    except Exception as e:
        logger.warning(f"5sim: ошибка бана #{order_id}: {e}")


async def _wait_for_code(order_id: str, timeout: int = 150) -> str | None:
    """Ждёт SMS-код. Polling /user/check/{id} каждые 3 секунды."""
    api_key = await get_setting("sms_api_key")
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    url = f"{FIVESIM_BASE}/user/check/{order_id}"

    async with aiohttp.ClientSession() as session:
        for attempt in range(timeout // 3):
            try:
                async with session.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        if attempt % 10 == 0:
                            logger.debug(f"5sim check #{order_id}: HTTP {resp.status}")
                        await asyncio.sleep(3)
                        continue

                    data = await resp.json()
                    status = data.get("status", "")
                    sms_list = data.get("sms", [])

                    if status == "RECEIVED" and sms_list:
                        code = sms_list[0].get("code", "")
                        if code:
                            logger.info(f"SMS-код получен для #{order_id}: {code}")
                            return code

                    if status in ("CANCELED", "TIMEOUT", "BANNED"):
                        logger.warning(f"5sim #{order_id}: статус {status}")
                        return None

                    # PENDING — ждём дальше
                    if attempt % 10 == 0:
                        logger.debug(f"5sim check #{order_id}: {status} (попытка {attempt})")

            except Exception as e:
                logger.warning(f"5sim check запрос упал для #{order_id}: {e}")

            await asyncio.sleep(3)

    logger.warning(f"Таймаут ожидания SMS для #{order_id} ({timeout}с)")
    return None


# --- Регистрация ---

MAX_NUMBER_ATTEMPTS = 5


async def register_one_account(country: str = "russia",
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

    _SMS_TYPES = {SentCodeType.SMS, SentCodeType.FRAGMENT_SMS}

    # Цикл попыток — если номер уже зарегистрирован (код через APP), берём новый
    for attempt in range(1, MAX_NUMBER_ATTEMPTS + 1):
        if progress_callback:
            prefix = f"[{attempt}/{MAX_NUMBER_ATTEMPTS}] " if attempt > 1 else ""
            await progress_callback(f"{prefix}📱 Покупаю номер...")

        try:
            number_info = await _buy_number(country)
        except Exception as e:
            return {"ok": False, "error": f"Покупка номера: {e}"}

        phone = number_info["phone"]
        order_id = number_info["activation_id"]

        if progress_callback:
            prefix = f"[{attempt}/{MAX_NUMBER_ATTEMPTS}] " if attempt > 1 else ""
            await progress_callback(f"{prefix}📱 {phone}\n📡 Отправляю код...")

        # Создаём запись в БД
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
            code_type = sent_code.type
            logger.info(f"Авторег {phone}: тип кода — {code_type}")

            # Если код не через SMS — номер уже зарегистрирован, пробуем resend
            if code_type not in _SMS_TYPES:
                try:
                    sent_code = await client.resend_code(phone, sent_code.phone_code_hash)
                    code_type = sent_code.type
                    logger.info(f"Авторег {phone}: повторный тип — {code_type}")
                except Exception as e:
                    logger.warning(f"Авторег {phone}: resend_code не удался: {e}")

            # Всё ещё не SMS — номер занят, отменяем
            if code_type not in _SMS_TYPES:
                logger.warning(
                    f"Авторег {phone}: код через {code_type.name}, номер уже занят "
                    f"(попытка {attempt}/{MAX_NUMBER_ATTEMPTS})")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await _cleanup_account(acc_id, session_path)

                if progress_callback:
                    await progress_callback(
                        f"⚠️ {phone} уже в Telegram (код через {code_type.name})\n"
                        f"↩️ Отменяю номер...")
                await _cancel_order(order_id)

                if progress_callback:
                    await progress_callback(
                        f"⚠️ {phone} уже в Telegram, беру другой номер...")
                continue  # следующая попытка

            phone_code_hash = sent_code.phone_code_hash

            if progress_callback:
                await progress_callback(f"📱 {phone}\n📨 SMS\n⏳ Жду код...")

            # Ждём код
            code = await _wait_for_code(order_id, timeout=150)

            if not code:
                await _cancel_order(order_id)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await _cleanup_account(acc_id, session_path)
                return {"ok": False, "error": f"SMS не пришёл для {phone}"}

            if progress_callback:
                await progress_callback(f"📱 {phone}\n🔑 Код получен, регистрирую...")

            # Входим / регистрируемся
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
                    await _finish_order(order_id)
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    await _cleanup_account(acc_id, session_path)
                    return {"ok": False, "error": f"{phone} — требуется 2FA пароль"}
                else:
                    raise

            await client.disconnect()

            # Успех — обновляем БД
            await execute(
                "UPDATE accounts SET status = 'active', session_file = ? WHERE id = ?",
                (session_path + ".session", acc_id),
            )

            if proxy_row:
                await execute(
                    "UPDATE proxies SET account_id = ? WHERE id = ?",
                    (acc_id, proxy_row["id"]))

            await _finish_order(order_id)

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
            await _cancel_order(order_id)
            try:
                await client.disconnect()
            except Exception:
                pass
            await _cleanup_account(acc_id, session_path)
            return {"ok": False, "error": f"FloodWait: подождите {e.value} сек"}

        except PhoneNumberBanned:
            await _ban_order(order_id)
            try:
                await client.disconnect()
            except Exception:
                pass
            await _cleanup_account(acc_id, session_path)
            if progress_callback:
                await progress_callback(f"⚠️ {phone} забанен, беру другой номер...")
            continue

        except PhoneNumberInvalid:
            await _ban_order(order_id)
            try:
                await client.disconnect()
            except Exception:
                pass
            await _cleanup_account(acc_id, session_path)
            if progress_callback:
                await progress_callback(f"⚠️ {phone} невалидный, беру другой номер...")
            continue

        except Exception as e:
            await _cancel_order(order_id)
            try:
                await client.disconnect()
            except Exception:
                pass
            await _cleanup_account(acc_id, session_path)
            logger.error(f"Авторег ошибка: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    # Все попытки исчерпаны
    return {"ok": False, "error": f"Не удалось найти свободный номер за {MAX_NUMBER_ATTEMPTS} попыток"}


async def _cleanup_account(acc_id: int, session_path: str):
    """Удаляет аккаунт и session файл при неудаче."""
    from db.database import delete_account
    await delete_account(acc_id)
    for ext in (".session", ".session-journal", ".session-wal", ".session-shm"):
        f = session_path + ext
        if os.path.exists(f):
            os.remove(f)
