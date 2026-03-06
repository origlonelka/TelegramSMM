"""Накрутка: заказ SMM-услуг через LikeDrom API."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db.database import fetch_one
from services.boost_manager import (
    get_networks, get_categories, get_services_by_category_id, get_service,
    get_user_balance, create_boost_order, get_user_orders,
)
from services.user_manager import get_or_create_user

router = Router()


class BoostOrder(StatesGroup):
    link = State()
    quantity = State()


class TopupCustom(StatesGroup):
    amount = State()


# ─── Главное меню накрутки ─────────────────────────────────

@router.callback_query(F.data.in_({"platform_boost", "back_boost"}))
async def boost_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = callback.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    balance = await get_user_balance(user.id)
    networks = await get_networks()

    text = (
        f"🚀 <b>Накрутка</b>\n\n"
        f"💰 Баланс: <b>{balance:.2f} ₽</b>\n\n"
        f"Выберите соцсеть:"
    )

    buttons = []
    # Сети по 2 в ряд
    row = []
    for net in networks:
        row.append(InlineKeyboardButton(
            text=f"{net['label']} ({net['count']})",
            callback_data=f"bst_net_{net['code']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="bst_topup"),
        InlineKeyboardButton(text="📋 Мои заказы", callback_data="bst_orders"),
    ])
    buttons.append([
        InlineKeyboardButton(text="👤 Профиль", callback_data="bst_profile"),
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_platform"),
    ])

    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


# ─── Профиль накрутки ──────────────────────────────────────

@router.callback_query(F.data == "bst_profile")
async def boost_profile(callback: CallbackQuery):
    user = callback.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    balance = await get_user_balance(user.id)

    # Статистика заказов
    orders_row = await fetch_one(
        "SELECT COUNT(*) as total, "
        "COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END), 0) as done, "
        "COALESCE(SUM(price_rub), 0) as spent "
        "FROM boost_orders WHERE user_telegram_id = ?",
        (user.id,))

    # Рефералы
    ref_row = await fetch_one(
        "SELECT COUNT(*) as cnt FROM referrals WHERE referrer_telegram_id = ?",
        (user.id,))

    # Реферальная ссылка
    bot = callback.bot
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{user.id}"

    text = (
        f"👤 <b>Профиль — Накрутка</b>\n\n"
        f"💰 Баланс: <b>{balance:.2f} ₽</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"  Заказов: {orders_row['total']}\n"
        f"  Выполнено: {orders_row['done']}\n"
        f"  Потрачено: {orders_row['spent']:.2f} ₽\n\n"
        f"👥 <b>Рефералы:</b> {ref_row['cnt']}\n"
        f"🔗 Ваша ссылка:\n<code>{ref_link}</code>\n\n"
        f"<i>За первое пополнение приглашённого вы получаете 5% бонус!</i>"
    )

    buttons = [
        [InlineKeyboardButton(text="💰 Пополнить", callback_data="bst_topup")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_boost")],
    ]
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


# ─── Выбор сети → категории ────────────────────────────────

@router.callback_query(F.data.startswith("bst_net_"))
async def boost_network(callback: CallbackQuery):
    network = callback.data.replace("bst_net_", "")
    categories = await get_categories(network)

    from services.boost_manager import NETWORK_LABELS
    net_label = NETWORK_LABELS.get(network, network)

    # Если категорий нет — сразу показываем услуги
    if not categories:
        services = await get_services(network, "")
        if not services:
            # Попробуем все услуги сети (без фильтра по категории)
            from services.boost_manager import get_all_services_for_network
            services = await get_all_services_for_network(network)
        if not services:
            await callback.answer("Нет доступных услуг", show_alert=True)
            return

        buttons = []
        for svc in services[:20]:
            price_text = f"{svc['price_per_1k']:.2f}₽/1K"
            name_short = svc["name"][:35]
            buttons.append([InlineKeyboardButton(
                text=f"{name_short} — {price_text}",
                callback_data=f"bst_svc_{svc['id']}")])
        buttons.append([InlineKeyboardButton(
            text="◀️ Назад", callback_data="back_boost")])

        await callback.message.edit_text(
            f"{net_label}\n\nВыберите услугу:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML")
        await callback.answer()
        return

    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=f"{cat['name']} ({cat['count']})",
            callback_data=f"bst_cat_{network}_{cat['id']}")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data="back_boost")])

    await callback.message.edit_text(
        f"{net_label}\n\nВыберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


# ─── Категория → услуги ───────────────────────────────────

@router.callback_query(F.data.startswith("bst_cat_"))
async def boost_category(callback: CallbackQuery):
    # Format: bst_cat_{network}_{category_id}
    raw = callback.data.replace("bst_cat_", "")
    # category_id is always the last part after last _
    last_sep = raw.rfind("_")
    network = raw[:last_sep]
    category_id = int(raw[last_sep + 1:])

    services = await get_services_by_category_id(network, category_id)
    if not services:
        await callback.answer("Нет доступных услуг", show_alert=True)
        return

    # Название категории из первого сервиса
    cat_name = services[0].get("category", "")

    buttons = []
    for svc in services[:20]:
        price_text = f"{svc['price_per_1k']:.2f}₽/1K"
        name_short = svc["name"][:35]
        buttons.append([InlineKeyboardButton(
            text=f"{name_short} — {price_text}",
            callback_data=f"bst_svc_{svc['id']}")])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data=f"bst_net_{network}")])

    await callback.message.edit_text(
        f"📋 <b>{cat_name}</b>\n\nВыберите услугу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


# ─── Услуга → ввод ссылки ─────────────────────────────────

@router.callback_query(F.data.startswith("bst_svc_"))
async def boost_service_selected(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.replace("bst_svc_", ""))
    svc = await get_service(service_id)
    if not svc:
        await callback.answer("Услуга не найдена", show_alert=True)
        return

    await state.set_state(BoostOrder.link)
    await state.update_data(service_id=service_id)

    text = (
        f"🛒 <b>{svc['name']}</b>\n\n"
        f"💰 Цена: {svc['price_per_1k']:.2f} ₽ за 1000\n"
        f"📊 Мин: {svc['min_qty']} | Макс: {svc['max_qty']}\n\n"
        f"🔗 Введите ссылку:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_boost")]]),
        parse_mode="HTML")
    await callback.answer()


# ─── Ввод ссылки → количество ─────────────────────────────

@router.message(BoostOrder.link)
async def boost_enter_link(message: Message, state: FSMContext):
    link = message.text.strip()
    # LikeDrom принимает только ссылки, не @username
    if link.startswith("@"):
        link = f"https://t.me/{link.lstrip('@')}"
    if not link.startswith("http"):
        await message.answer("❌ Введите ссылку (например, https://t.me/channel):")
        return

    await state.update_data(link=link)
    data = await state.get_data()
    svc = await get_service(data["service_id"])

    await state.set_state(BoostOrder.quantity)
    await message.answer(
        f"🔗 Ссылка: <code>{link}</code>\n\n"
        f"🔢 Введите количество ({svc['min_qty']} – {svc['max_qty']}):",
        parse_mode="HTML")


# ─── Ввод количества → подтверждение ──────────────────────

@router.message(BoostOrder.quantity)
async def boost_enter_quantity(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите число:")
        return

    quantity = int(message.text.strip())
    data = await state.get_data()
    svc = await get_service(data["service_id"])

    if quantity < svc["min_qty"]:
        await message.answer(f"❌ Минимум: {svc['min_qty']}")
        return
    if quantity > svc["max_qty"]:
        await message.answer(f"❌ Максимум: {svc['max_qty']}")
        return

    price = round(svc["price_per_1k"] * quantity / 1000, 2)
    balance = await get_user_balance(message.from_user.id)

    await state.update_data(quantity=quantity, price=price)

    text = (
        f"📋 <b>Подтверждение заказа</b>\n\n"
        f"🔧 {svc['name']}\n"
        f"🔗 {data['link']}\n"
        f"🔢 Количество: {quantity}\n"
        f"💰 Стоимость: <b>{price:.2f} ₽</b>\n"
        f"💳 Баланс: {balance:.2f} ₽\n"
    )

    if balance < price:
        text += f"\n❌ <b>Недостаточно средств!</b> Нужно ещё {price - balance:.2f} ₽"
        buttons = [
            [InlineKeyboardButton(text="💰 Пополнить", callback_data="bst_topup")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_boost")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="✅ Заказать", callback_data="bst_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_boost")],
        ]

    await message.answer(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")


# ─── Подтверждение заказа ─────────────────────────────────

@router.callback_query(F.data == "bst_confirm")
async def boost_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "service_id" not in data:
        await callback.answer("Данные заказа утеряны", show_alert=True)
        await state.clear()
        return

    await state.clear()
    result = await create_boost_order(
        callback.from_user.id,
        data["service_id"],
        data["link"],
        data["quantity"],
    )

    if result["ok"]:
        balance = await get_user_balance(callback.from_user.id)
        await callback.message.edit_text(
            f"✅ <b>Заказ #{result['order_id']} создан!</b>\n\n"
            f"💰 Списано: {result['price']:.2f} ₽\n"
            f"💳 Остаток: {balance:.2f} ₽\n\n"
            f"Статус можно проверить в «Мои заказы».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Мои заказы", callback_data="bst_orders")],
                [InlineKeyboardButton(text="◀️ Меню", callback_data="back_boost")],
            ]),
            parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"❌ <b>Ошибка</b>\n\n{result['error']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_boost")]]),
            parse_mode="HTML")
    await callback.answer()


# ─── Мои заказы ───────────────────────────────────────────

@router.callback_query(F.data == "bst_orders")
async def boost_orders(callback: CallbackQuery):
    orders = await get_user_orders(callback.from_user.id, limit=15)

    if not orders:
        await callback.message.edit_text(
            "📋 <b>Мои заказы</b>\n\nУ вас ещё нет заказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_boost")]]),
            parse_mode="HTML")
        await callback.answer()
        return

    status_emoji = {
        "pending": "⏳", "processing": "🔄", "in_progress": "🔄",
        "completed": "✅", "partial": "⚠️", "canceled": "❌", "error": "❌",
    }

    lines = ["📋 <b>Мои заказы</b>\n"]
    for o in orders:
        emoji = status_emoji.get(o["status"], "❓")
        name = (o["service_name"] or "")[:25]
        lines.append(
            f"{emoji} #{o['id']} | {name} | {o['quantity']} шт | "
            f"{o['price_rub']:.2f}₽")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="bst_orders")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_boost")]]),
        parse_mode="HTML")
    await callback.answer()


# ─── Пополнение баланса ──────────────────────────────────

@router.callback_query(F.data == "bst_topup")
async def boost_topup_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    balance = await get_user_balance(callback.from_user.id)

    buttons = [
        [InlineKeyboardButton(text="50 ₽", callback_data="bst_pay_50"),
         InlineKeyboardButton(text="100 ₽", callback_data="bst_pay_100")],
        [InlineKeyboardButton(text="250 ₽", callback_data="bst_pay_250"),
         InlineKeyboardButton(text="500 ₽", callback_data="bst_pay_500")],
        [InlineKeyboardButton(text="1000 ₽", callback_data="bst_pay_1000"),
         InlineKeyboardButton(text="✏️ Другая сумма", callback_data="bst_pay_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_boost")],
    ]

    await callback.message.edit_text(
        f"💰 <b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{balance:.2f} ₽</b>\n\n"
        f"Выберите сумму:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("bst_pay_") & ~F.data.endswith("custom"))
async def boost_topup_quick(callback: CallbackQuery):
    amount = int(callback.data.replace("bst_pay_", ""))
    await _create_topup(callback, amount)


@router.callback_query(F.data == "bst_pay_custom")
async def boost_topup_custom_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TopupCustom.amount)
    await callback.message.edit_text(
        "💰 Введите сумму пополнения (от 50 ₽):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bst_topup")]]),
        parse_mode="HTML")
    await callback.answer()


@router.message(TopupCustom.amount)
async def boost_topup_custom_value(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        amount = float(text)
    except ValueError:
        await message.answer("❌ Введите число:")
        return
    if amount < 50:
        await message.answer("❌ Минимум 50 ₽:")
        return
    if amount > 100000:
        await message.answer("❌ Максимум 100 000 ₽:")
        return

    await state.clear()
    # Создаём фейковый callback для переиспользования
    from services.payment_manager import create_topup_payment
    result = await create_topup_payment(message.from_user.id, amount)
    if result["ok"]:
        buttons = [
            [InlineKeyboardButton(
                text="💳 Оплатить", url=result["confirmation_url"])],
            [InlineKeyboardButton(
                text="🔄 Проверить оплату",
                callback_data=f"bst_check_{result['payment_id']}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="bst_topup")],
        ]
        await message.answer(
            f"💰 <b>Пополнение на {amount:.0f} ₽</b>\n\n"
            f"Нажмите «Оплатить» для перехода к оплате.\n"
            f"После оплаты нажмите «Проверить оплату».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML")
    else:
        await message.answer(f"❌ {result['error']}")


async def _create_topup(callback: CallbackQuery, amount: float):
    """Создаёт платёж YooKassa для пополнения баланса."""
    from services.payment_manager import create_topup_payment
    result = await create_topup_payment(callback.from_user.id, amount)

    if result["ok"]:
        buttons = [
            [InlineKeyboardButton(
                text="💳 Оплатить", url=result["confirmation_url"])],
            [InlineKeyboardButton(
                text="🔄 Проверить оплату",
                callback_data=f"bst_check_{result['payment_id']}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="bst_topup")],
        ]
        await callback.message.edit_text(
            f"💰 <b>Пополнение на {amount:.0f} ₽</b>\n\n"
            f"Нажмите «Оплатить» для перехода к оплате.\n"
            f"После оплаты нажмите «Проверить оплату».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"❌ {result['error']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="bst_topup")]]),
            parse_mode="HTML")
    await callback.answer()


# ─── Проверка оплаты пополнения ───────────────────────────

@router.callback_query(F.data.startswith("bst_check_"))
async def boost_check_payment(callback: CallbackQuery):
    payment_uuid = callback.data.replace("bst_check_", "")
    from services.payment_manager import check_topup_status
    result = await check_topup_status(payment_uuid)

    if result.get("paid"):
        balance = await get_user_balance(callback.from_user.id)
        await callback.message.edit_text(
            f"✅ <b>Оплата прошла!</b>\n\n"
            f"💰 Зачислено: {result.get('amount', 0):.2f} ₽\n"
            f"💳 Баланс: {balance:.2f} ₽",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Меню", callback_data="back_boost")]]),
            parse_mode="HTML")
    elif result.get("status") == "pending":
        await callback.answer("⏳ Оплата ещё не поступила. Попробуйте позже.",
                              show_alert=True)
    else:
        await callback.answer(f"❌ Статус: {result.get('status', 'неизвестно')}",
                              show_alert=True)
