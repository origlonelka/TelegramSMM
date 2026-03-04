"""Payment flow handlers: plan selection, payment creation, status checking."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.keyboards.inline import (
    plans_list_kb, payment_created_kb, paywall_kb, main_menu_kb,
)
from services.payment_manager import (
    get_active_plans, create_payment, check_payment_status,
)

router = Router()


@router.callback_query(F.data == "select_plan")
async def show_plans(callback: CallbackQuery):
    """Show available subscription plans."""
    plans = await get_active_plans()
    if not plans:
        await callback.answer(
            "Тарифы временно недоступны", show_alert=True)
        return

    text = "💳 <b>Выберите тариф</b>\n\n"
    for plan in plans:
        per_month = plan["price_rub"] / (plan["duration_days"] / 30)
        savings = ""
        if plan["duration_days"] > 30:
            monthly_plan = next(
                (p for p in plans if p["duration_days"] == 30), None)
            if monthly_plan:
                full_price = monthly_plan["price_rub"] * (
                    plan["duration_days"] / 30)
                discount = int((1 - plan["price_rub"] / full_price) * 100)
                if discount > 0:
                    savings = f" (скидка {discount}%)"

        text += (
            f"<b>{plan['name']}</b> — {plan['price_rub']} ₽{savings}\n"
            f"  ~{per_month:.0f} ₽/мес\n\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=plans_list_kb(plans),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_plan_"))
async def initiate_payment(callback: CallbackQuery):
    """User selected a plan — create YooKassa payment."""
    plan_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    await callback.answer("Создаю платёж...")

    result = await create_payment(user_id, plan_id)
    if not result["ok"]:
        await callback.message.edit_text(
            f"❌ Ошибка: {result['error']}",
            reply_markup=paywall_kb(show_trial=False),
            parse_mode="HTML",
        )
        return

    payment_uuid = result["payment_id"]
    confirmation_url = result["confirmation_url"]

    text = (
        "💳 <b>Оплата</b>\n\n"
        "Нажмите кнопку ниже, чтобы перейти к оплате.\n"
        "После оплаты нажмите «Проверить оплату» или дождитесь "
        "автоматического подтверждения."
    )

    await callback.message.edit_text(
        text,
        reply_markup=payment_created_kb(confirmation_url, payment_uuid),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("pay_check_"))
async def check_payment(callback: CallbackQuery):
    """User manually checks payment status."""
    payment_uuid = callback.data[len("pay_check_"):]

    result = await check_payment_status(payment_uuid)

    if result["paid"]:
        await callback.message.edit_text(
            "✅ <b>Оплата подтверждена!</b>\n\n"
            "Подписка активирована. Выберите раздел:",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer("Оплата подтверждена!")
    elif result["status"] == "cancelled":
        await callback.message.edit_text(
            "❌ <b>Платёж отменён</b>\n\n"
            "Вы можете выбрать тариф заново:",
            reply_markup=paywall_kb(show_trial=False),
            parse_mode="HTML",
        )
        await callback.answer()
    elif result["status"] in ("pending", "waiting_for_capture"):
        await callback.answer(
            "⏳ Оплата ещё не поступила. Попробуйте через минуту.",
            show_alert=True,
        )
    else:
        await callback.answer(
            f"Статус: {result['status']}. Попробуйте позже.",
            show_alert=True,
        )


@router.callback_query(F.data == "pay_cancel")
async def cancel_payment(callback: CallbackQuery):
    """Return to plan selection."""
    await show_plans(callback)
