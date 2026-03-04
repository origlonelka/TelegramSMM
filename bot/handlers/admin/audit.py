"""Admin audit log viewer."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.database import fetch_all

router = Router()

ROLE_HIERARCHY = {"superadmin": 4, "admin": 3, "finance": 2, "support": 1}


def _check_role(admin: dict, min_role: str = "admin") -> bool:
    return ROLE_HIERARCHY.get(admin["role"], 0) >= ROLE_HIERARCHY.get(min_role, 99)


@router.callback_query(F.data == "adm_audit")
async def audit_menu(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await _show_audit(callback, 0)


@router.callback_query(F.data.startswith("adm_audit_page_"))
async def audit_page(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    offset = int(callback.data.replace("adm_audit_page_", ""))
    await _show_audit(callback, offset)


async def _show_audit(callback: CallbackQuery, offset: int):
    page_size = 15
    logs = await fetch_all(
        "SELECT a.*, adm.username as actor_name FROM audit_logs a "
        "LEFT JOIN admins adm ON a.actor_user_id = adm.user_id "
        "ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
        (page_size + 1, offset))

    has_next = len(logs) > page_size
    logs = logs[:page_size]

    lines = [f"📋 <b>Аудит лог</b> (стр. {offset // page_size + 1})\n"]
    if not logs:
        lines.append("Нет записей.")
    else:
        for l in logs:
            actor = f"@{l['actor_name']}" if l["actor_name"] else str(l["actor_user_id"])
            ts = l["created_at"][:16] if l["created_at"] else ""
            entity = f" {l['entity_type']}#{l['entity_id']}" if l["entity_type"] else ""
            lines.append(f"{ts} {actor}: {l['action']}{entity}")

    buttons = []
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="◀️ Пред.", callback_data=f"adm_audit_page_{max(0, offset - page_size)}"))
    if has_next:
        nav.append(InlineKeyboardButton(
            text="След. ▶️", callback_data=f"adm_audit_page_{offset + page_size}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()
