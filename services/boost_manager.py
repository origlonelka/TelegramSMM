"""Business logic for SMM boosting (накрутка) via LikeDrom."""
import logging
from db.database import execute, fetch_one, fetch_all
from services import likedrom

logger = logging.getLogger(__name__)

DEFAULT_MARKUP = 40  # % наценки по умолчанию

# Маппинг сетей для красивых названий
NETWORK_LABELS = {
    "telegram": "📱 Telegram",
    "instagram": "📷 Instagram",
    "youtube": "📺 YouTube",
    "tiktok": "🎵 TikTok",
    "vk": "🔵 ВКонтакте",
    "twitter": "🐦 Twitter",
    "facebook": "👤 Facebook",
    "ok": "🟠 Одноклассники",
    "likee": "❤️ Likee",
}


async def _get_markup() -> float:
    row = await fetch_one(
        "SELECT value FROM bot_settings WHERE key = 'boost_markup_percent'")
    return float(row["value"]) if row else DEFAULT_MARKUP


async def sync_services():
    """Загружает сервисы из LikeDrom, применяет наценку, сохраняет в БД."""
    services = await likedrom.get_services()
    markup = await _get_markup()
    multiplier = 1 + markup / 100

    count = 0
    for svc in services:
        sid = int(svc.get("service", 0))
        if not sid:
            continue

        name = svc.get("name", "")
        category = svc.get("category", "")
        network = (svc.get("network", "") or "").lower().strip()
        min_qty = int(svc.get("min", 0))
        max_qty = int(svc.get("max", 0))

        # Цена за 1000 единиц
        rate = float(svc.get("rate", 0))
        cost_per_1k = rate  # цена LikeDrom
        price_per_1k = round(rate * multiplier, 2)  # наша цена

        # Проверяем, существует ли уже запись
        existing = await fetch_one(
            "SELECT id FROM boost_services WHERE id = ?", (sid,))
        if existing:
            await execute(
                "UPDATE boost_services SET name=?, category=?, network=?, "
                "min_qty=?, max_qty=?, cost_per_1k=?, price_per_1k=?, "
                "updated_at=datetime('now') WHERE id=?",
                (name, category, network, min_qty, max_qty,
                 cost_per_1k, price_per_1k, sid))
        else:
            await execute(
                "INSERT INTO boost_services "
                "(id, name, category, network, min_qty, max_qty, "
                "cost_per_1k, price_per_1k) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, name, category, network, min_qty, max_qty,
                 cost_per_1k, price_per_1k))
        count += 1

    logger.info(f"Синхронизировано {count} сервисов LikeDrom (наценка {markup}%)")
    return count


async def get_networks() -> list[dict]:
    """Уникальные сети с количеством активных сервисов."""
    rows = await fetch_all(
        "SELECT network, COUNT(*) as cnt FROM boost_services "
        "WHERE is_active = 1 AND network != '' "
        "GROUP BY network ORDER BY cnt DESC")
    result = []
    for r in rows:
        net = r["network"]
        label = NETWORK_LABELS.get(net, net.capitalize())
        result.append({"code": net, "label": label, "count": r["cnt"]})
    return result


async def get_categories(network: str) -> list[dict]:
    """Категории сервисов для конкретной сети."""
    rows = await fetch_all(
        "SELECT category, COUNT(*) as cnt FROM boost_services "
        "WHERE is_active = 1 AND network = ? AND category != '' "
        "GROUP BY category ORDER BY cnt DESC",
        (network,))
    return [{"name": r["category"], "count": r["cnt"]} for r in rows]


async def get_services(network: str, category: str) -> list[dict]:
    """Список услуг для сети и категории."""
    rows = await fetch_all(
        "SELECT * FROM boost_services "
        "WHERE is_active = 1 AND network = ? AND category = ? "
        "ORDER BY price_per_1k ASC",
        (network, category))
    return [dict(r) for r in rows]


async def get_service(service_id: int) -> dict | None:
    row = await fetch_one(
        "SELECT * FROM boost_services WHERE id = ?", (service_id,))
    return dict(row) if row else None


async def get_user_balance(user_tg_id: int) -> float:
    row = await fetch_one(
        "SELECT balance_rub FROM users WHERE telegram_id = ?", (user_tg_id,))
    return float(row["balance_rub"]) if row and row["balance_rub"] else 0.0


async def create_boost_order(user_tg_id: int, service_id: int,
                              link: str, quantity: int) -> dict:
    """Создаёт заказ: проверяет баланс, списывает, отправляет в LikeDrom."""
    svc = await get_service(service_id)
    if not svc:
        return {"ok": False, "error": "Услуга не найдена"}

    # Рассчитать стоимость
    price_per_1k = svc["price_per_1k"]
    cost_per_1k = svc["cost_per_1k"]
    price = round(price_per_1k * quantity / 1000, 2)
    cost = round(cost_per_1k * quantity / 1000, 2)

    if quantity < svc["min_qty"]:
        return {"ok": False, "error": f"Минимум: {svc['min_qty']}"}
    if quantity > svc["max_qty"]:
        return {"ok": False, "error": f"Максимум: {svc['max_qty']}"}

    # Проверить баланс
    balance = await get_user_balance(user_tg_id)
    if balance < price:
        return {"ok": False, "error": f"Недостаточно средств. Нужно {price:.2f} ₽, баланс {balance:.2f} ₽"}

    # Списать с баланса
    await execute(
        "UPDATE users SET balance_rub = balance_rub - ? WHERE telegram_id = ?",
        (price, user_tg_id))

    # Создать запись заказа
    await execute(
        "INSERT INTO boost_orders "
        "(user_telegram_id, service_id, service_name, link, quantity, "
        "price_rub, cost_rub, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (user_tg_id, service_id, svc["name"], link, quantity, price, cost))

    order_row = await fetch_one(
        "SELECT id FROM boost_orders WHERE user_telegram_id = ? "
        "ORDER BY id DESC LIMIT 1", (user_tg_id,))
    local_order_id = order_row["id"]

    # Отправить в LikeDrom
    try:
        ld_order_id = await likedrom.create_order(service_id, link, quantity)
        await execute(
            "UPDATE boost_orders SET likedrom_order_id = ?, status = 'processing' "
            "WHERE id = ?", (ld_order_id, local_order_id))
        return {
            "ok": True,
            "order_id": local_order_id,
            "likedrom_order_id": ld_order_id,
            "price": price,
        }
    except Exception as e:
        # Ошибка LikeDrom — возврат средств
        await execute(
            "UPDATE users SET balance_rub = balance_rub + ? WHERE telegram_id = ?",
            (price, user_tg_id))
        await execute(
            "UPDATE boost_orders SET status = 'error' WHERE id = ?",
            (local_order_id,))
        logger.error(f"LikeDrom order failed: {e}")
        return {"ok": False, "error": f"Ошибка сервиса: {e}"}


async def update_order_statuses():
    """Обновляет статусы незавершённых заказов из LikeDrom."""
    rows = await fetch_all(
        "SELECT id, likedrom_order_id, price_rub, cost_rub, user_telegram_id "
        "FROM boost_orders "
        "WHERE status IN ('pending', 'processing', 'in_progress') "
        "AND likedrom_order_id IS NOT NULL")

    for r in rows:
        try:
            data = await likedrom.check_order(r["likedrom_order_id"])
            ld_status = (data.get("status", "") or "").lower().strip()

            status_map = {
                "completed": "completed",
                "partial": "partial",
                "canceled": "canceled",
                "processing": "processing",
                "pending": "processing",
                "in progress": "in_progress",
            }
            new_status = status_map.get(ld_status, "processing")

            await execute(
                "UPDATE boost_orders SET status = ?, updated_at = datetime('now') "
                "WHERE id = ?", (new_status, r["id"]))

            # Частичный заказ — возврат за недовыполненное
            if new_status in ("partial", "canceled"):
                charge = float(data.get("charge", 0))
                if charge < r["cost_rub"]:
                    # Считаем, сколько реально списал LikeDrom vs наша цена
                    ratio = charge / r["cost_rub"] if r["cost_rub"] > 0 else 0
                    actual_price = round(r["price_rub"] * ratio, 2)
                    refund = round(r["price_rub"] - actual_price, 2)
                    if refund > 0:
                        await execute(
                            "UPDATE users SET balance_rub = balance_rub + ? "
                            "WHERE telegram_id = ?",
                            (refund, r["user_telegram_id"]))

        except Exception as e:
            logger.warning(f"Check order #{r['id']} failed: {e}")


async def get_user_orders(user_tg_id: int, limit: int = 10) -> list[dict]:
    rows = await fetch_all(
        "SELECT * FROM boost_orders WHERE user_telegram_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (user_tg_id, limit))
    return [dict(r) for r in rows]


async def topup_balance(user_tg_id: int, amount: float):
    """Зачисляет средства на баланс (после успешной оплаты)."""
    await execute(
        "UPDATE users SET balance_rub = balance_rub + ? WHERE telegram_id = ?",
        (amount, user_tg_id))

    # Реферальный бонус при первом пополнении
    ref_row = await fetch_one(
        "SELECT referrer_telegram_id FROM users WHERE telegram_id = ?",
        (user_tg_id,))
    if ref_row and ref_row["referrer_telegram_id"]:
        # Проверяем, что это первое пополнение
        prev = await fetch_one(
            "SELECT COUNT(*) as c FROM balance_topups "
            "WHERE user_telegram_id = ? AND status = 'succeeded'",
            (user_tg_id,))
        if prev and prev["c"] <= 1:  # текущее пополнение может уже быть записано
            ref_pct_row = await fetch_one(
                "SELECT value FROM bot_settings WHERE key = 'boost_referral_percent'")
            ref_pct = float(ref_pct_row["value"]) if ref_pct_row else 5.0
            bonus = round(amount * ref_pct / 100, 2)
            if bonus > 0:
                referrer_id = ref_row["referrer_telegram_id"]
                await execute(
                    "UPDATE users SET balance_rub = balance_rub + ? "
                    "WHERE telegram_id = ?", (bonus, referrer_id))
                logger.info(
                    f"Реферальный бонус {bonus}₽ для #{referrer_id} "
                    f"(приглашённый #{user_tg_id} пополнил {amount}₽)")
                return {"referrer_id": referrer_id, "bonus": bonus}
    return None
