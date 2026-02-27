import os
import logging
from db.database import fetch_one, fetch_all
from services.account_manager import ensure_connected
from services.spintax import spin

logger = logging.getLogger(__name__)

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)


async def apply_template(acc, template) -> dict:
    """Применяет шаблон профиля к аккаунту.

    Поля first_name, last_name, bio поддерживают spintax:
      {Алексей|Дмитрий|Иван} → случайный вариант для каждого аккаунта.
    """
    try:
        client = await ensure_connected(acc)
        me = await client.get_me()

        first_name = spin(template["first_name"]) if template["first_name"] else me.first_name
        last_name = spin(template["last_name"]) if template["last_name"] else ""
        bio = spin(template["bio"]) if template["bio"] else ""

        # Обновляем профиль
        await client.update_profile(
            first_name=first_name,
            last_name=last_name,
            bio=bio,
        )

        # Устанавливаем фото, если указано
        if template["photo_path"] and os.path.exists(template["photo_path"]):
            await client.set_profile_photo(photo=template["photo_path"])

        logger.info(
            f"Шаблон «{template['name']}» применён к аккаунту #{acc['id']} "
            f"({first_name} {last_name})"
        )
        return {"ok": True, "first_name": first_name, "last_name": last_name}

    except Exception as e:
        logger.error(f"Ошибка применения шаблона к аккаунту #{acc['id']}: {e}")
        return {"ok": False, "error": str(e)}


async def apply_template_to_all(template_id: int) -> dict:
    """Применяет шаблон ко всем активным аккаунтам."""
    template = await fetch_one(
        "SELECT * FROM account_templates WHERE id = ?", (template_id,))
    if not template:
        return {"ok": False, "error": "Шаблон не найден"}

    accounts = await fetch_all("SELECT * FROM accounts WHERE status = 'active'")
    if not accounts:
        return {"ok": False, "error": "Нет активных аккаунтов"}

    success = 0
    errors = 0
    for acc in accounts:
        result = await apply_template(acc, template)
        if result["ok"]:
            success += 1
        else:
            errors += 1

    return {"ok": True, "success": success, "errors": errors, "total": len(accounts)}
