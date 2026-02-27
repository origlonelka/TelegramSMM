from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    accounts_menu_kb, account_list_kb, account_item_kb,
    acc_confirm_del_kb, back_kb,
)

router = Router()


class AddAccount(StatesGroup):
    phone = State()
    api_id = State()
    api_hash = State()
    proxy = State()


class AuthAccount(StatesGroup):
    code = State()


class EditProxy(StatesGroup):
    value = State()


# --- Меню аккаунтов ---

@router.callback_query(F.data == "accounts")
async def accounts_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    count = await fetch_one("SELECT COUNT(*) as cnt FROM accounts")
    text = f"📱 <b>Аккаунты</b>\n\nВсего: {count['cnt']}"
    await callback.message.edit_text(text, reply_markup=accounts_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "acc_list")
async def acc_list(callback: CallbackQuery):
    accounts = await fetch_all("SELECT id, phone, status FROM accounts ORDER BY id")
    if not accounts:
        await callback.answer("Список пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Список аккаунтов:</b>",
        reply_markup=account_list_kb(accounts),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр аккаунта ---

@router.callback_query(F.data.startswith("acc_view_"))
async def acc_view(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[2])
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))
    if not acc:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return
    status_icon = "🟢" if acc["status"] == "active" else "🔴"
    proxy_display = f"<code>{acc['proxy']}</code>" if acc["proxy"] else "не задан"
    text = (
        f"📱 <b>Аккаунт #{acc['id']}</b>\n\n"
        f"Телефон: <code>{acc['phone']}</code>\n"
        f"Статус: {status_icon} {acc['status']}\n"
        f"Прокси: {proxy_display}\n"
        f"Комментариев сегодня: {acc['comments_today']}\n"
        f"Комментариев за час: {acc['comments_hour']}\n"
        f"Добавлен: {acc['added_at']}"
    )
    await callback.message.edit_text(text, reply_markup=account_item_kb(acc_id), parse_mode="HTML")
    await callback.answer()


# --- Добавление ---

@router.callback_query(F.data == "acc_add")
async def acc_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddAccount.phone)
    await callback.message.edit_text(
        "📱 Введите номер телефона (в формате +79001234567):",
        reply_markup=back_kb("accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddAccount.phone)
async def acc_add_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Неверный формат. Введите номер в формате +79001234567:")
        return
    existing = await fetch_one("SELECT id FROM accounts WHERE phone = ?", (phone,))
    if existing:
        await message.answer("❌ Аккаунт с таким номером уже существует.")
        await state.clear()
        return
    await state.update_data(phone=phone)
    await state.set_state(AddAccount.api_id)
    await message.answer("🔑 Введите API ID:")


@router.message(AddAccount.api_id)
async def acc_add_api_id(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ API ID должен быть числом. Попробуйте снова:")
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(AddAccount.api_hash)
    await message.answer("🔑 Введите API Hash:")


@router.message(AddAccount.api_hash)
async def acc_add_api_hash(message: Message, state: FSMContext):
    api_hash = message.text.strip()
    await state.update_data(api_hash=api_hash)
    await state.set_state(AddAccount.proxy)
    await message.answer(
        "🌐 Введите прокси (необязательно):\n\n"
        "Форматы:\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>http://host:port</code>\n"
        "<code>socks5://host:port</code>\n\n"
        "Или отправьте <b>-</b> чтобы пропустить.",
        parse_mode="HTML",
    )


@router.message(AddAccount.proxy)
async def acc_add_proxy(message: Message, state: FSMContext):
    proxy_text = message.text.strip()
    proxy = None if proxy_text == "-" else proxy_text
    data = await state.get_data()
    await state.clear()

    acc_id = await execute_returning(
        "INSERT INTO accounts (phone, api_id, api_hash, proxy) VALUES (?, ?, ?, ?)",
        (data["phone"], data["api_id"], data["api_hash"], proxy),
    )
    await message.answer(
        f"✅ Аккаунт <code>{data['phone']}</code> добавлен (#{acc_id}).\n\n"
        f"Теперь авторизуйте его через меню аккаунта.",
        reply_markup=account_item_kb(acc_id),
        parse_mode="HTML",
    )


# --- Удаление ---

@router.callback_query(F.data.startswith("acc_del_confirm_"))
async def acc_del_confirm(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[3])
    await execute("DELETE FROM accounts WHERE id = ?", (acc_id,))
    await callback.message.edit_text(
        "✅ Аккаунт удалён.",
        reply_markup=accounts_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acc_del_"))
async def acc_del(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[2])
    acc = await fetch_one("SELECT phone FROM accounts WHERE id = ?", (acc_id,))
    await callback.message.edit_text(
        f"🗑 Удалить аккаунт <code>{acc['phone']}</code>?",
        reply_markup=acc_confirm_del_kb(acc_id),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Авторизация ---

@router.callback_query(F.data.startswith("acc_auth_"))
async def acc_auth_start(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))
    if not acc:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

    from services.account_manager import send_code
    result = await send_code(acc)
    if not result["ok"]:
        await callback.message.edit_text(
            f"❌ Ошибка: {result['error']}",
            reply_markup=account_item_kb(acc_id),
        )
        await callback.answer()
        return

    await state.set_state(AuthAccount.code)
    await state.update_data(acc_id=acc_id, phone_code_hash=result["phone_code_hash"])
    await callback.message.edit_text(
        f"📲 Код подтверждения отправлен на <code>{acc['phone']}</code>.\n"
        f"Введите код:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AuthAccount.code)
async def acc_auth_code(message: Message, state: FSMContext):
    data = await state.get_data()
    acc_id = data["acc_id"]
    code = message.text.strip()

    from services.account_manager import sign_in
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))
    result = await sign_in(acc, code, data["phone_code_hash"])
    await state.clear()

    if not result["ok"]:
        await message.answer(
            f"❌ Ошибка авторизации: {result['error']}",
            reply_markup=account_item_kb(acc_id),
        )
        return

    await execute("UPDATE accounts SET status = 'active' WHERE id = ?", (acc_id,))
    await message.answer(
        f"✅ Аккаунт успешно авторизован!",
        reply_markup=account_item_kb(acc_id),
    )


# --- Редактирование прокси ---

@router.callback_query(F.data.startswith("acc_proxy_"))
async def acc_proxy_edit(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    await state.set_state(EditProxy.value)
    await state.update_data(acc_id=acc_id)
    await callback.message.edit_text(
        "🌐 Введите новый прокси:\n\n"
        "Форматы:\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>http://host:port</code>\n"
        "<code>socks5://host:port</code>\n\n"
        "Или отправьте <b>-</b> чтобы убрать прокси.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditProxy.value)
async def acc_proxy_save(message: Message, state: FSMContext):
    data = await state.get_data()
    acc_id = data["acc_id"]
    proxy_text = message.text.strip()
    proxy = None if proxy_text == "-" else proxy_text
    await state.clear()

    await execute("UPDATE accounts SET proxy = ? WHERE id = ?", (proxy, acc_id))

    # Сбрасываем клиент чтобы пересоздать с новым прокси
    from services.account_manager import disconnect
    await disconnect(acc_id)

    await message.answer(
        f"✅ Прокси {'обновлён' if proxy else 'удалён'}.",
        reply_markup=account_item_kb(acc_id),
    )
