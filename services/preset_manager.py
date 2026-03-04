import logging
from db.database import execute, fetch_one, fetch_all, execute_returning
from services.account_setup import apply_template

logger = logging.getLogger(__name__)


async def activate_preset(preset_id: int) -> dict:
    """Активирует пресет: создаёт кампанию для каждого режима, применяет профиль.

    1. Деактивирует все кампании
    2. Создаёт по одной кампании для каждого выбранного режима
    3. Привязывает каналы, сообщения, все активные аккаунты к каждой кампании
    4. Запускает все кампании
    5. Применяет шаблон профиля ко всем аккаунтам
    """
    preset = await fetch_one("SELECT * FROM presets WHERE id = ?", (preset_id,))
    if not preset:
        return {"ok": False, "error": "Пресет не найден"}

    # 1. Деактивируем все кампании
    await execute("UPDATE campaigns SET is_active = 0")

    # Парсим режимы (мультивыбор через запятую)
    modes = (preset["mode"] or "comments").split(",")

    # Подготавливаем данные пресета
    preset_channels = await fetch_all(
        "SELECT channel_id FROM preset_channels WHERE preset_id = ?", (preset_id,))
    preset_messages = await fetch_all(
        "SELECT message_id FROM preset_messages WHERE preset_id = ?", (preset_id,))
    accounts = await fetch_all("SELECT id FROM accounts WHERE status = 'active'")

    from bot.keyboards.inline import MODE_LABELS

    # 2. Удаляем старую кампанию пресета если была
    old_camp_id = preset["campaign_id"]
    if old_camp_id:
        await execute("UPDATE logs SET campaign_id = NULL WHERE campaign_id = ?", (old_camp_id,))
        await execute("DELETE FROM campaign_channels WHERE campaign_id = ?", (old_camp_id,))
        await execute("DELETE FROM campaign_accounts WHERE campaign_id = ?", (old_camp_id,))
        await execute("DELETE FROM campaign_messages WHERE campaign_id = ?", (old_camp_id,))
        await execute("DELETE FROM campaigns WHERE id = ?", (old_camp_id,))

    # 3. Создаём по одной кампании на каждый режим
    campaign_ids = []
    first_camp_id = None
    for mode in modes:
        mode_label = MODE_LABELS.get(mode, mode)
        camp_name = f"📦 {preset['name']}"
        if len(modes) > 1:
            camp_name = f"📦 {preset['name']} [{mode_label}]"

        camp_id = await execute_returning(
            "INSERT INTO campaigns (name, mode, delay_min, delay_max, hourly_limit, daily_limit, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (camp_name, mode,
             preset["delay_min"], preset["delay_max"],
             preset["hourly_limit"], preset["daily_limit"]),
        )
        campaign_ids.append(camp_id)
        if first_camp_id is None:
            first_camp_id = camp_id

        # Привязываем каналы
        for ch in preset_channels:
            await execute(
                "INSERT OR IGNORE INTO campaign_channels (campaign_id, channel_id) VALUES (?, ?)",
                (camp_id, ch["channel_id"]),
            )

        # Привязываем сообщения
        for msg in preset_messages:
            await execute(
                "INSERT OR IGNORE INTO campaign_messages (campaign_id, message_id) VALUES (?, ?)",
                (camp_id, msg["message_id"]),
            )

        # Привязываем все активные аккаунты
        for acc in accounts:
            await execute(
                "INSERT OR IGNORE INTO campaign_accounts (campaign_id, account_id) VALUES (?, ?)",
                (camp_id, acc["id"]),
            )

    # Сохраняем первую кампанию как основную для пресета
    await execute(
        "UPDATE presets SET campaign_id = ? WHERE id = ?", (first_camp_id, preset_id))

    # 4. Применяем шаблон профиля
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

    mode_labels = [MODE_LABELS.get(m, m) for m in modes]
    logger.info(
        f"Пресет «{preset['name']}» активирован: "
        f"режимы={', '.join(mode_labels)}, кампаний={len(campaign_ids)}, "
        f"каналов={len(preset_channels)}, сообщений={len(preset_messages)}, "
        f"аккаунтов={len(accounts)}")

    return {
        "ok": True,
        "campaign_id": first_camp_id,
        "campaign_ids": campaign_ids,
        "modes": modes,
        "channels": len(preset_channels),
        "messages": len(preset_messages),
        "accounts": len(accounts),
        "profile": profile_results,
    }
