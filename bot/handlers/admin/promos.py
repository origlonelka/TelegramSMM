"""Admin promo code management: create, list, delete."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, fetch_all, fetch_one
from services.audit import log_action
import secrets

router = Router()

ROLE_HIERARCHY = {"superadmin": 4, "admin": 3, "finance": 2, "support": 1}


class CreatePromo(StatesGroup):
    code = State()
    type_ = State()
    value = State()
    max_uses = State()


def _check_role(admin: dict, min_role: str = "admin") -> bool:
    return ROLE_HIERARCHY.get(admin["role"], 0) >= ROLE_HIERARCHY.get(min_role, 99)


@router.callback_query(F.data == "adm_promos")
async def promos_menu(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    promos = await fetch_all(
        "SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 20")
    lines = ["🎟 <b>Промокоды</b>\n"]
    buttons = []
    for p in promos:
        uses = f"{p['uses_count']}/{p['max_uses']}" if p["max_uses"] else f"{p['uses_count']}/∞"
        valid = f" до {p['valid_until'][:10]}" if p["valid_until"] else ""
        lines.append(f"<code>{p['code']}</code> — {p['type']} {p['value']}{'%' if p['type'] == 'discount' else ' дн.'} ({uses}){valid}")
        buttons.append([InlineKeyboardButton(
            text=f"❌ {p['code']}",
            callback_data=f"adm_promo_del_{p['id']}")])

    buttons.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm_promo_create")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_promo_create")
async def promo_create_start(callback: CallbackQuery, state: FSMContext, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.set_state(CreatePromo.type_)
    await callback.message.edit_text(
        "Выберите тип промокода:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Скидка (%)", callback_data="adm_promo_type_discount")],
            [InlineKeyboardButton(text="📅 Бонус дней", callback_data="adm_promo_type_bonus_days")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm_promos")],
        ]))
    await callback.answer()


@router.callback_query(F.data.startswith("adm_promo_type_"))
async def promo_select_type(callback: CallbackQuery, state: FSMContext):
    promo_type = callback.data.replace("adm_promo_type_", "")
    await state.update_data(promo_type=promo_type)
    await state.set_state(CreatePromo.value)
    label = "скидку в %" if promo_type == "discount" else "количество бонусных дней"
    await callback.message.edit_text(
        f"Введите {label}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm_promos")],
        ]))
    await callback.answer()


@router.message(CreatePromo.value)
async def promo_enter_value(message: Message, state: FSMContext, admin: dict):
    try:
        value = float(message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число.")
        return
    await state.update_data(value=value)
    await state.set_state(CreatePromo.max_uses)
    await message.answer(
        "Введите макс. количество использований (0 = без лимита):")


@router.message(CreatePromo.max_uses)
async def promo_enter_max_uses(message: Message, state: FSMContext, admin: dict):
    try:
        max_uses = int(message.text.strip())
        if max_uses < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите неотрицательное целое число.")
        return

    data = await state.get_data()
    await state.clear()

    code = secrets.token_hex(4).upper()
    await execute(
        "INSERT INTO promo_codes (code, type, value, max_uses, created_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, data["promo_type"], data["value"], max_uses, admin["user_id"]))
    await log_action(admin["user_id"], "promo_created", "promo", 0,
                     {"code": code, "type": data["promo_type"],
                      "value": data["value"], "max_uses": max_uses})
    await message.answer(
        f"✅ Промокод создан: <code>{code}</code>\n"
        f"Тип: {data['promo_type']}, значение: {data['value']}, "
        f"макс. использований: {max_uses or '∞'}",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_promo_del_"))
async def promo_delete(callback: CallbackQuery, admin: dict):
    if not _check_role(admin):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    promo_id = int(callback.data.replace("adm_promo_del_", ""))
    promo = await fetch_one("SELECT code FROM promo_codes WHERE id = ?", (promo_id,))
    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return
    await execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
    await log_action(admin["user_id"], "promo_deleted", "promo", promo_id,
                     {"code": promo["code"]})
    await callback.answer("Промокод удалён")
    await promos_menu(callback, admin)
