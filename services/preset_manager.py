import logging
from db.database import execute, fetch_one, fetch_all, execute_returning
from services.account_setup import apply_template

logger = logging.getLogger(__name__)


async def activate_preset(preset_id: int) -> dict:
    """Активирует пресет: создаёт/обновляет кампанию, применяет профиль.

    1. Деактивирует все кампании
    2. Создаёт или обновляет кампанию для пресета
    3. Привязывает каналы, сообщения, все активные аккаунты
    4. Запускает кампанию
    5. Применяет шаблон профиля ко всем аккаунтам
    """
    preset = await fetch_one("SELECT * FROM presets WHERE id = ?", (preset_id,))
    if not preset:
        return {"ok": False, "error": "Пресет не найден"}

    # 1. Деактивируем все кампании
    await execute("UPDATE campaigns SET is_active = 0")

    # 2. Находим или создаём кампанию для пресета
    camp_id = preset["campaign_id"]
    if camp_id:
        camp = await fetch_one("SELECT id FROM campaigns WHERE id = ?", (camp_id,))
        if not camp:
            camp_id = None

    if not camp_id:
        camp_id = await execute_returning(
            "INSERT INTO campaigns (name, mode, delay_min, delay_max, hourly_limit, daily_limit, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (f"📦 {preset['name']}", preset["mode"] or "comments",
             preset["delay_min"], preset["delay_max"],
             preset["hourly_limit"], preset["daily_limit"]),
        )
        await execute(
            "UPDATE presets SET campaign_id = ? WHERE id = ?", (camp_id, preset_id))
    else:
        await execute(
            "UPDATE campaigns SET name = ?, mode = ?, delay_min = ?, delay_max = ?, "
            "hourly_limit = ?, daily_limit = ?, is_active = 1 WHERE id = ?",
            (f"📦 {preset['name']}", preset["mode"] or "comments",
             preset["delay_min"], preset["delay_max"],
             preset["hourly_limit"], preset["daily_limit"], camp_id),
        )

    # 3. Очищаем привязки кампании
    await execute("DELETE FROM campaign_channels WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_accounts WHERE campaign_id = ?", (camp_id,))
    await execute("DELETE FROM campaign_messages WHERE campaign_id = ?", (camp_id,))

    # 4. Привязываем каналы из пресета
    preset_channels = await fetch_all(
        "SELECT channel_id FROM preset_channels WHERE preset_id = ?", (preset_id,))
    for ch in preset_channels:
        await execute(
            "INSERT OR IGNORE INTO campaign_channels (campaign_id, channel_id) VALUES (?, ?)",
            (camp_id, ch["channel_id"]),
        )

    # 5. Привязываем сообщения из пресета
    preset_messages = await fetch_all(
        "SELECT message_id FROM preset_messages WHERE preset_id = ?", (preset_id,))
    for msg in preset_messages:
        await execute(
            "INSERT OR IGNORE INTO campaign_messages (campaign_id, message_id) VALUES (?, ?)",
            (camp_id, msg["message_id"]),
        )

    # 6. Привязываем все активные аккаунты
    accounts = await fetch_all("SELECT id FROM accounts WHERE status = 'active'")
    for acc in accounts:
        await execute(
            "INSERT OR IGNORE INTO campaign_accounts (campaign_id, account_id) VALUES (?, ?)",
            (camp_id, acc["id"]),
        )

    # 7. Применяем шаблон профиля
    profile_results = {"applied": False, "success": 0, "errors": 0}
    if preset["template_id"]:
        template = await fetch_one(
            "SELECT * FROM account_templates WHERE id = ?", (preset["template_id"],))
        if template:
            accounts_full = await fetch_all(
                "SELECT * FROM accounts WHERE status = 'active'")
            for acc in accounts_full:
                result = await apply_template(acc, template)
                if result["ok"]:
                    profile_results["success"] += 1
                else:
                    profile_results["errors"] += 1
            profile_results["applied"] = True

    logger.info(
        f"Пресет «{preset['name']}» активирован: кампания #{camp_id}, "
        f"каналов={len(preset_channels)}, сообщений={len(preset_messages)}, "
        f"аккаунтов={len(accounts)}")

    return {
        "ok": True,
        "campaign_id": camp_id,
        "channels": len(preset_channels),
        "messages": len(preset_messages),
        "accounts": len(accounts),
        "profile": profile_results,
    }
