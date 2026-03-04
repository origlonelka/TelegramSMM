"""Admin finance: plan management, payment journal, CSV export."""
import csv
import io
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, fetch_all, fetch_one
from services.audit import log_action

router = Router()

ROLE_HIERARCHY = {"superadmin": 4, "admin": 3, "finance": 2, "support": 1}


class EditPlan(StatesGroup):
    price = State()


def _check_role(admin: dict, min_role: str = "finance") -> bool:
    return ROLE_HIERARCHY.get(admin["role"], 0) >= ROLE_HIERARCHY.get(min_role, 99)


@router.callback_query(F.data == "adm_plans")
async def plans_menu(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    plans = await fetch_all(
        "SELECT * FROM subscription_plans ORDER BY duration_days")
    lines = ["💳 <b>Тарифные планы</b>\n"]
    buttons = []
    for p in plans:
        status = "🟢" if p["is_active"] else "🔴"
        lines.append(f"{status} {p['name']} — {p['price_rub']} ₽ ({p['duration_days']} дн.)")
        buttons.append([InlineKeyboardButton(
            text=f"{'🔴' if p['is_active'] else '🟢'} {p['name']}",
            callback_data=f"adm_plan_toggle_{p['id']}")])

    buttons.append([InlineKeyboardButton(text="📥 Экспорт платежей CSV", callback_data="adm_export_payments")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_plan_toggle_"))
async def plan_toggle(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    plan_id = int(callback.data.replace("adm_plan_toggle_", ""))
    plan = await fetch_one("SELECT is_active FROM subscription_plans WHERE id = ?", (plan_id,))
    if not plan:
        await callback.answer("План не найден", show_alert=True)
        return
    new_status = 0 if plan["is_active"] else 1
    await execute("UPDATE subscription_plans SET is_active = ? WHERE id = ?",
                  (new_status, plan_id))
    await log_action(admin["user_id"], "plan_toggled", "plan", plan_id,
                     {"is_active": new_status})
    await callback.answer("Статус изменён")
    await plans_menu(callback, admin)


@router.callback_query(F.data == "adm_export_payments")
async def export_payments(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    rows = await fetch_all(
        "SELECT s.id, s.user_telegram_id, u.username, p.name as plan_name, "
        "s.amount_rub, s.status, s.started_at, s.expires_at, s.created_at "
        "FROM subscriptions s "
        "LEFT JOIN users u ON s.user_telegram_id = u.telegram_id "
        "LEFT JOIN subscription_plans p ON s.plan_id = p.id "
        "ORDER BY s.created_at DESC")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Telegram ID", "Username", "План", "Сумма",
                      "Статус", "Начало", "Окончание", "Создано"])
    for r in rows:
        writer.writerow([r["id"], r["user_telegram_id"], r["username"] or "",
                          r["plan_name"] or "", r["amount_rub"], r["status"],
                          r["started_at"] or "", r["expires_at"] or "", r["created_at"]])

    data = buf.getvalue().encode("utf-8-sig")
    doc = BufferedInputFile(data, filename="payments.csv")
    await callback.message.answer_document(doc, caption="📥 Экспорт платежей")
    await callback.answer()
