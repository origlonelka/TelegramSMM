from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards.inline import (
    autoreg_menu_kb, autoreg_country_kb, back_kb,
)

router = Router()


class SetSmsKey(StatesGroup):
    key = State()


class SetAutoregCount(StatesGroup):
    count = State()


# --- Меню ---

@router.callback_query(F.data.in_({"autoreg", "back_autoreg"}))
async def autoreg_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from services.autoreg import get_setting, get_balance, COUNTRIES

    api_key = await get_setting("sms_api_key")
    key_status = "✅ Настроен" if api_key else "❌ Не настроен"

    country = int(await get_setting("autoreg_country") or "0")
    country_name = COUNTRIES.get(country, f"#{country}")
    count = int(await get_setting("autoreg_count") or "1")

    balance_text = ""
    if api_key:
        try:
            balance = await get_balance()
            balance_text = f"\n💰 Баланс: {balance:.2f} ₽"
        except Exception:
            balance_text = "\n💰 Баланс: ошибка"

    text = (
        f"🤖 <b>Авторегистрация</b>\n\n"
        f"SMS-сервис: {key_status}{balance_text}\n"
        f"🌍 Страна: {country_name}\n"
        f"🔢 Количество: {count}\n\n"
        f"Используется hero-sms.com для получения SMS.\n"
        f"Прокси из пула назначаются автоматически."
    )
    await callback.message.edit_text(
        text, reply_markup=autoreg_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Настройка SMS API ключа ---

@router.callback_query(F.data == "areg_set_key")
async def areg_set_key_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetSmsKey.key)
    await callback.message.edit_text(
        "🔑 <b>HeroSMS API ключ</b>\n\n"
        "Получите ключ на <b>hero-sms.com</b>:\n"
        "Профиль → API → Скопировать ключ\n\n"
        "Вставьте ключ:",
        reply_markup=back_kb("autoreg"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SetSmsKey.key)
async def areg_set_key_value(message: Message, state: FSMContext):
    key = message.text.strip()
    if len(key) < 10:
        await message.answer("❌ Ключ слишком короткий. Попробуйте снова:")
        return
    await state.clear()

    from services.autoreg import set_setting
    await set_setting("sms_api_key", key)

    # Проверяем ключ
    from services.autoreg import get_balance
    try:
        balance = await get_balance()
        await message.answer(
            f"✅ Ключ сохранён!\n💰 Баланс: {balance:.2f} ₽",
            reply_markup=autoreg_menu_kb(),
        )
    except Exception as e:
        await message.answer(
            f"⚠️ Ключ сохранён, но проверка не прошла:\n<code>{e}</code>",
            reply_markup=autoreg_menu_kb(),
            parse_mode="HTML",
        )


# --- Выбор страны ---

@router.callback_query(F.data == "areg_country")
async def areg_country(callback: CallbackQuery):
    from services.autoreg import get_setting, get_all_min_prices
    current = int(await get_setting("autoreg_country") or "0")
    prices = await get_all_min_prices()
    await callback.message.edit_text(
        "🌍 Выберите страну для покупки номеров:",
        reply_markup=autoreg_country_kb(current, prices),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("areg_setcountry_"))
async def areg_setcountry(callback: CallbackQuery):
    country = int(callback.data.split("_")[2])
    from services.autoreg import set_setting, COUNTRIES, get_all_min_prices
    await set_setting("autoreg_country", str(country))
    await callback.answer(f"✅ Страна: {COUNTRIES.get(country, '?')}")

    prices = await get_all_min_prices()
    await callback.message.edit_text(
        "🌍 Выберите страну для покупки номеров:",
        reply_markup=autoreg_country_kb(country, prices),
    )


# --- Количество ---

@router.callback_query(F.data == "areg_count")
async def areg_count_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetAutoregCount.count)
    await callback.message.edit_text(
        "🔢 Сколько аккаунтов зарегистрировать?\n\n"
        "Введите число (1–20):",
        reply_markup=back_kb("autoreg"),
    )
    await callback.answer()


@router.message(SetAutoregCount.count)
async def areg_count_value(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите число:")
        return
    count = int(message.text.strip())
    if count < 1 or count > 20:
        await message.answer("❌ Допустимо от 1 до 20:")
        return
    await state.clear()

    from services.autoreg import set_setting
    await set_setting("autoreg_count", str(count))
    await message.answer(
        f"✅ Количество: {count}",
        reply_markup=autoreg_menu_kb(),
    )


# --- Запуск ---

@router.callback_query(F.data == "areg_start")
async def areg_start(callback: CallbackQuery):
    from services.autoreg import get_setting, register_one_account

    api_key = await get_setting("sms_api_key")
    if not api_key:
        await callback.answer("❌ Сначала настройте SMS API ключ", show_alert=True)
        return

    country = int(await get_setting("autoreg_country") or "0")
    count = int(await get_setting("autoreg_count") or "1")

    from services.autoreg import COUNTRIES
    country_name = COUNTRIES.get(country, f"#{country}")

    await callback.message.edit_text(
        f"🤖 <b>Авторегистрация</b>\n\n"
        f"🌍 {country_name} | 🔢 {count} шт.\n\n"
        f"⏳ Запускаю...",
        parse_mode="HTML",
    )
    await callback.answer()

    success = 0
    errors = 0
    results_text = ""

    for i in range(count):
        # Прогресс-коллбэк: обновляет сообщение
        async def progress(text, _i=i):
            nonlocal results_text
            await callback.message.edit_text(
                f"🤖 <b>Авторегистрация ({_i + 1}/{count})</b>\n\n"
                f"{text}\n\n"
                f"{results_text}",
                parse_mode="HTML",
            )

        result = await register_one_account(
            country=country,
            progress_callback=progress,
        )

        if result["ok"]:
            success += 1
            status = "новый" if result.get("is_new") else "существующий"
            results_text += f"✅ {result['phone']} — {status}\n"
        else:
            errors += 1
            results_text += f"❌ {result['error']}\n"

            # Если FloodWait — останавливаемся
            if "FloodWait" in result["error"]:
                results_text += "⛔ Остановлено из-за FloodWait\n"
                break

    # Итог
    await callback.message.edit_text(
        f"🤖 <b>Авторегистрация завершена</b>\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибки: {errors}\n\n"
        f"{results_text}",
        reply_markup=autoreg_menu_kb(),
        parse_mode="HTML",
    )


# --- Баланс ---

@router.callback_query(F.data == "areg_balance")
async def areg_balance(callback: CallbackQuery):
    from services.autoreg import get_balance
    try:
        balance = await get_balance()
        await callback.answer(f"💰 Баланс: {balance:.2f} ₽", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ {e}", show_alert=True)
