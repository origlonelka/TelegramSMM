import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one, delete_account
from bot.keyboards.inline import (
    accounts_menu_kb, account_list_kb, account_item_kb,
    acc_confirm_del_kb, acc_add_method_kb, back_kb,
)

router = Router()


# --- FSM States ---

class AddAccount(StatesGroup):
    """Полное добавление: телефон + api_id + api_hash + прокси."""
    phone = State()
    api_id = State()
    api_hash = State()
    proxy = State()


class AddQuick(StatesGroup):
    """Быстрое добавление: только телефон + прокси (API из .env)."""
    phone = State()
    proxy = State()


class AddSession(StatesGroup):
    """Импорт через session string."""
    session_string = State()
    api_id = State()
    api_hash = State()
    proxy = State()


class AddSessionFile(StatesGroup):
    """Импорт через .session файл."""
    file = State()
    api_id = State()
    api_hash = State()
    proxy = State()


class AddTdata(StatesGroup):
    """Импорт через tdata (ZIP архив)."""
    file = State()
    api_id = State()
    api_hash = State()
    proxy = State()


class AuthAccount(StatesGroup):
    code = State()


class Auth2FA(StatesGroup):
    password = State()


class EditProxy(StatesGroup):
    value = State()


# --- Меню аккаунтов ---

@router.callback_query(F.data.in_({"accounts", "back_accounts"}))
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


# ============================================================
# ДОБАВЛЕНИЕ АККАУНТОВ — выбор способа
# ============================================================

@router.callback_query(F.data == "acc_add")
async def acc_add_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "📱 <b>Выберите способ добавления аккаунта:</b>\n\n"
        "• <b>Телефон + SMS</b> — ввести телефон, API ID, API Hash\n"
        "• <b>Быстрое</b> — только телефон (API из .env)\n"
        "• <b>Session string</b> — вставить строку сессии\n"
        "• <b>Session файл</b> — отправить .session файл\n"
        "• <b>Tdata</b> — ZIP архив с папкой tdata",
        reply_markup=acc_add_method_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ============================================================
# Способ 1: Телефон + API ID + API Hash + SMS
# ============================================================

@router.callback_query(F.data == "acc_add_phone")
async def acc_add_phone_start(callback: CallbackQuery, state: FSMContext):
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
        "<code>http://host:port</code>\n\n"
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


# ============================================================
# Способ 2: Быстрое добавление (API из .env)
# ============================================================

@router.callback_query(F.data == "acc_add_quick")
async def acc_add_quick_start(callback: CallbackQuery, state: FSMContext):
    from core.config import API_ID, API_HASH
    if not API_ID or not API_HASH:
        await callback.answer(
            "❌ API_ID и API_HASH не заданы в .env",
            show_alert=True,
        )
        return
    await state.set_state(AddQuick.phone)
    await callback.message.edit_text(
        "⚡ <b>Быстрое добавление</b>\n\n"
        "API ID и API Hash будут взяты из .env.\n\n"
        "📱 Введите номер телефона (в формате +79001234567):",
        reply_markup=back_kb("accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddQuick.phone)
async def acc_quick_phone(message: Message, state: FSMContext):
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
    await state.set_state(AddQuick.proxy)
    await message.answer(
        "🌐 Введите прокси или <b>-</b> чтобы пропустить:",
        parse_mode="HTML",
    )


@router.message(AddQuick.proxy)
async def acc_quick_proxy(message: Message, state: FSMContext):
    from core.config import API_ID, API_HASH
    proxy_text = message.text.strip()
    proxy = None if proxy_text == "-" else proxy_text
    data = await state.get_data()
    await state.clear()

    acc_id = await execute_returning(
        "INSERT INTO accounts (phone, api_id, api_hash, proxy) VALUES (?, ?, ?, ?)",
        (data["phone"], API_ID, API_HASH, proxy),
    )
    await message.answer(
        f"✅ Аккаунт <code>{data['phone']}</code> добавлен (#{acc_id}).\n\n"
        f"Теперь авторизуйте его через меню аккаунта.",
        reply_markup=account_item_kb(acc_id),
        parse_mode="HTML",
    )


# ============================================================
# Способ 3: Session string
# ============================================================

@router.callback_query(F.data == "acc_add_session")
async def acc_add_session_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddSession.session_string)
    await callback.message.edit_text(
        "📋 <b>Импорт через Session String</b>\n\n"
        "Вставьте строку сессии Pyrogram:\n"
        "(получить можно через <code>client.export_session_string()</code>)",
        reply_markup=back_kb("accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddSession.session_string)
async def acc_session_string(message: Message, state: FSMContext):
    session_str = message.text.strip()
    if len(session_str) < 50:
        await message.answer("❌ Слишком короткая строка. Проверьте и попробуйте снова:")
        return
    await state.update_data(session_string=session_str)

    from core.config import API_ID, API_HASH
    if API_ID and API_HASH:
        # API есть в .env — предложим использовать их
        await state.update_data(api_id=API_ID, api_hash=API_HASH)
        await state.set_state(AddSession.proxy)
        await message.answer(
            f"🔑 API ID/Hash будут взяты из .env.\n\n"
            f"🌐 Введите прокси или <b>-</b> чтобы пропустить:",
            parse_mode="HTML",
        )
    else:
        await state.set_state(AddSession.api_id)
        await message.answer("🔑 Введите API ID:")


@router.message(AddSession.api_id)
async def acc_session_api_id(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ API ID должен быть числом:")
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(AddSession.api_hash)
    await message.answer("🔑 Введите API Hash:")


@router.message(AddSession.api_hash)
async def acc_session_api_hash(message: Message, state: FSMContext):
    await state.update_data(api_hash=message.text.strip())
    await state.set_state(AddSession.proxy)
    await message.answer(
        "🌐 Введите прокси или <b>-</b> чтобы пропустить:",
        parse_mode="HTML",
    )


@router.message(AddSession.proxy)
async def acc_session_proxy(message: Message, state: FSMContext):
    proxy_text = message.text.strip()
    proxy = None if proxy_text == "-" else proxy_text
    data = await state.get_data()
    await state.clear()

    # Сначала создаём запись чтобы получить id для файла сессии
    acc_id = await execute_returning(
        "INSERT INTO accounts (phone, api_id, api_hash, proxy, status) VALUES (?, ?, ?, ?, 'importing')",
        ("importing...", data["api_id"], data["api_hash"], proxy),
    )

    await message.answer("⏳ Импортирую сессию...")

    from services.account_manager import import_session_string
    result = await import_session_string(
        session_string=data["session_string"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
        acc_id=acc_id,
        proxy_str=proxy,
    )

    if not result["ok"]:
        await delete_account(acc_id)
        await message.answer(
            f"❌ Ошибка импорта: {result['error']}",
            reply_markup=acc_add_method_kb(),
        )
        return

    phone = result["phone"]
    await execute(
        "UPDATE accounts SET phone = ?, status = 'active' WHERE id = ?",
        (phone, acc_id),
    )
    await message.answer(
        f"✅ Аккаунт <code>{phone}</code> импортирован и активен (#{acc_id})!",
        reply_markup=account_item_kb(acc_id),
        parse_mode="HTML",
    )


# ============================================================
# Способ 4: Session файл (.session)
# ============================================================

@router.callback_query(F.data == "acc_add_file")
async def acc_add_file_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddSessionFile.file)
    await callback.message.edit_text(
        "📁 <b>Импорт .session файла</b>\n\n"
        "Отправьте файл сессии Pyrogram (.session).\n"
        "Файл будет скопирован в папку sessions/.",
        reply_markup=back_kb("accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddSessionFile.file, F.document)
async def acc_file_received(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.endswith(".session"):
        await message.answer("❌ Нужен файл с расширением .session. Попробуйте снова:")
        return

    # Скачиваем файл во временную директорию
    tmp_path = f"/tmp/tg_session_{doc.file_id}.session"
    await message.bot.download(doc.file_id, destination=tmp_path)
    await state.update_data(file_path=tmp_path)

    from core.config import API_ID, API_HASH
    if API_ID and API_HASH:
        await state.update_data(api_id=API_ID, api_hash=API_HASH)
        await state.set_state(AddSessionFile.proxy)
        await message.answer(
            "🔑 API ID/Hash будут взяты из .env.\n\n"
            "🌐 Введите прокси или <b>-</b> чтобы пропустить:",
            parse_mode="HTML",
        )
    else:
        await state.set_state(AddSessionFile.api_id)
        await message.answer("🔑 Введите API ID:")


@router.message(AddSessionFile.file)
async def acc_file_not_document(message: Message, state: FSMContext):
    await message.answer("❌ Отправьте файл (.session), а не текст.")


@router.message(AddSessionFile.api_id)
async def acc_file_api_id(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ API ID должен быть числом:")
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(AddSessionFile.api_hash)
    await message.answer("🔑 Введите API Hash:")


@router.message(AddSessionFile.api_hash)
async def acc_file_api_hash(message: Message, state: FSMContext):
    await state.update_data(api_hash=message.text.strip())
    await state.set_state(AddSessionFile.proxy)
    await message.answer(
        "🌐 Введите прокси или <b>-</b> чтобы пропустить:",
        parse_mode="HTML",
    )


@router.message(AddSessionFile.proxy)
async def acc_file_proxy(message: Message, state: FSMContext):
    proxy_text = message.text.strip()
    proxy = None if proxy_text == "-" else proxy_text
    data = await state.get_data()
    await state.clear()

    acc_id = await execute_returning(
        "INSERT INTO accounts (phone, api_id, api_hash, proxy, status) VALUES (?, ?, ?, ?, 'importing')",
        ("importing...", data["api_id"], data["api_hash"], proxy),
    )

    await message.answer("⏳ Импортирую сессию из файла...")

    from services.account_manager import import_session_file
    result = await import_session_file(
        file_path=data["file_path"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
        acc_id=acc_id,
        proxy_str=proxy,
    )

    # Удаляем временный файл
    tmp_path = data.get("file_path")
    if tmp_path and os.path.exists(tmp_path):
        os.remove(tmp_path)

    if not result["ok"]:
        await delete_account(acc_id)
        await message.answer(
            f"❌ Ошибка импорта: {result['error']}",
            reply_markup=acc_add_method_kb(),
        )
        return

    phone = result["phone"]
    await execute(
        "UPDATE accounts SET phone = ?, status = 'active' WHERE id = ?",
        (phone, acc_id),
    )
    await message.answer(
        f"✅ Аккаунт <code>{phone}</code> импортирован и активен (#{acc_id})!",
        reply_markup=account_item_kb(acc_id),
        parse_mode="HTML",
    )


# ============================================================
# Способ 5: Tdata (ZIP архив)
# ============================================================

@router.callback_query(F.data == "acc_add_tdata")
async def acc_add_tdata_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTdata.file)
    await callback.message.edit_text(
        "📂 <b>Импорт через tdata</b>\n\n"
        "Заархивируйте папку <code>tdata</code> в ZIP и отправьте сюда.\n\n"
        "Папка tdata находится:\n"
        "• Windows: <code>%APPDATA%/Telegram Desktop/tdata</code>\n"
        "• Linux: <code>~/.local/share/TelegramDesktop/tdata</code>\n"
        "• macOS: <code>~/Library/Application Support/Telegram Desktop/tdata</code>",
        reply_markup=back_kb("accounts"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddTdata.file, F.document)
async def acc_tdata_received(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.lower().endswith(".zip"):
        await message.answer("❌ Нужен ZIP-архив. Заархивируйте папку tdata и отправьте снова:")
        return

    await message.answer("⏳ Скачиваю архив...")
    tmp_path = f"/tmp/tdata_{doc.file_id}.zip"
    await message.bot.download(doc.file_id, destination=tmp_path)
    await state.update_data(zip_path=tmp_path)

    from core.config import API_ID, API_HASH
    if API_ID and API_HASH:
        await state.update_data(api_id=API_ID, api_hash=API_HASH)
        await state.set_state(AddTdata.proxy)
        await message.answer(
            "🔑 API ID/Hash будут взяты из .env.\n\n"
            "🌐 Введите прокси или <b>-</b> чтобы пропустить:",
            parse_mode="HTML",
        )
    else:
        await state.set_state(AddTdata.api_id)
        await message.answer("🔑 Введите API ID:")


@router.message(AddTdata.file)
async def acc_tdata_not_document(message: Message, state: FSMContext):
    await message.answer("❌ Отправьте ZIP-архив с папкой tdata, а не текст.")


@router.message(AddTdata.api_id)
async def acc_tdata_api_id(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ API ID должен быть числом:")
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(AddTdata.api_hash)
    await message.answer("🔑 Введите API Hash:")


@router.message(AddTdata.api_hash)
async def acc_tdata_api_hash(message: Message, state: FSMContext):
    await state.update_data(api_hash=message.text.strip())
    await state.set_state(AddTdata.proxy)
    await message.answer(
        "🌐 Введите прокси или <b>-</b> чтобы пропустить:",
        parse_mode="HTML",
    )


@router.message(AddTdata.proxy)
async def acc_tdata_proxy(message: Message, state: FSMContext):
    proxy_text = message.text.strip()
    proxy = None if proxy_text == "-" else proxy_text
    data = await state.get_data()
    await state.clear()

    acc_id = await execute_returning(
        "INSERT INTO accounts (phone, api_id, api_hash, proxy, status) VALUES (?, ?, ?, ?, 'importing')",
        ("importing...", data["api_id"], data["api_hash"], proxy),
    )

    await message.answer("⏳ Импортирую tdata... Это может занять несколько секунд.")

    from services.account_manager import import_tdata
    result = await import_tdata(
        zip_path=data["zip_path"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
        acc_id=acc_id,
        proxy_str=proxy,
    )

    # Удаляем временный ZIP
    zip_path = data.get("zip_path")
    if zip_path and os.path.exists(zip_path):
        os.remove(zip_path)

    if not result["ok"]:
        await delete_account(acc_id)
        await message.answer(
            f"❌ Ошибка импорта tdata: {result['error']}",
            reply_markup=acc_add_method_kb(),
        )
        return

    phone = result["phone"]
    await execute(
        "UPDATE accounts SET phone = ?, status = 'active' WHERE id = ?",
        (phone, acc_id),
    )
    await message.answer(
        f"✅ Аккаунт <code>{phone}</code> импортирован из tdata и активен (#{acc_id})!",
        reply_markup=account_item_kb(acc_id),
        parse_mode="HTML",
    )


# ============================================================
# Проверка аккаунтов
# ============================================================

@router.callback_query(F.data == "acc_check_all")
async def acc_check_all(callback: CallbackQuery):
    accounts = await fetch_all("SELECT * FROM accounts ORDER BY id")
    if not accounts:
        await callback.answer("Нет аккаунтов для проверки", show_alert=True)
        return

    await callback.message.edit_text(
        f"🔍 Проверяю {len(accounts)} аккаунтов...",
        parse_mode="HTML",
    )
    await callback.answer()

    from services.account_manager import check_account
    valid = 0
    dead = 0
    unreachable = 0
    deleted_phones = []
    warn_phones = []

    for acc in accounts:
        result = await check_account(acc)
        if result["ok"]:
            valid += 1
            if result.get("phone"):
                await execute(
                    "UPDATE accounts SET phone = ?, status = 'active' WHERE id = ?",
                    (result["phone"], acc["id"]),
                )
        elif result.get("dead"):
            dead += 1
            deleted_phones.append(acc["phone"])
            await delete_account(acc["id"])
            session_file = os.path.join("sessions", f"account_{acc['id']}.session")
            if os.path.exists(session_file):
                os.remove(session_file)
        else:
            unreachable += 1
            warn_phones.append(acc["phone"])

    text = f"🔍 <b>Проверка завершена</b>\n\n✅ Валидных: {valid}"
    if dead:
        text += f"\n❌ Мёртвых (удалены): {dead}"
    if unreachable:
        text += f"\n⚠️ Нет связи (не удалены): {unreachable}"
    if deleted_phones:
        phones_list = "\n".join(f"• <code>{p}</code>" for p in deleted_phones)
        text += f"\n\n🗑 Удалены:\n{phones_list}"
    if warn_phones:
        phones_list = "\n".join(f"• <code>{p}</code>" for p in warn_phones)
        text += f"\n\n⚠️ Проверьте прокси:\n{phones_list}"

    await callback.message.edit_text(
        text,
        reply_markup=accounts_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("acc_check_"))
async def acc_check(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[2])
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))
    if not acc:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

    await callback.message.edit_text(
        f"🔍 Проверяю аккаунт <code>{acc['phone']}</code>...",
        parse_mode="HTML",
    )
    await callback.answer()

    from services.account_manager import check_account
    result = await check_account(acc)

    if result["ok"]:
        if result.get("phone"):
            await execute(
                "UPDATE accounts SET phone = ?, status = 'active' WHERE id = ?",
                (result["phone"], acc_id),
            )
        await callback.message.edit_text(
            f"✅ Аккаунт <code>{acc['phone']}</code> — валиден!",
            reply_markup=account_item_kb(acc_id),
            parse_mode="HTML",
        )
    elif result.get("dead"):
        # Мёртвый аккаунт — удаляем
        await delete_account(acc_id)
        session_file = os.path.join("sessions", f"account_{acc_id}.session")
        if os.path.exists(session_file):
            os.remove(session_file)
        await callback.message.edit_text(
            f"❌ Аккаунт <code>{acc['phone']}</code> мёртв — удалён.\n\n"
            f"Ошибка: <code>{result['error'][:200]}</code>",
            reply_markup=accounts_menu_kb(),
            parse_mode="HTML",
        )
    else:
        # Ошибка сети/таймаут — не удаляем
        await callback.message.edit_text(
            f"⚠️ Аккаунт <code>{acc['phone']}</code> — не удалось подключиться.\n\n"
            f"<code>{result['error'][:200]}</code>\n\n"
            f"Аккаунт <b>не удалён</b>. Проверьте прокси или сеть.",
            reply_markup=account_item_kb(acc_id),
            parse_mode="HTML",
        )


# ============================================================
# Удаление
# ============================================================

@router.callback_query(F.data.startswith("acc_del_confirm_"))
async def acc_del_confirm(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[3])
    await delete_account(acc_id)
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


# ============================================================
# Авторизация: SMS код + 2FA пароль
# ============================================================

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

    if result.get("need_2fa"):
        # Аккаунт с двухфакторной аутентификацией
        await state.set_state(Auth2FA.password)
        await state.update_data(acc_id=acc_id)
        await message.answer(
            "🔐 Аккаунт защищён двухфакторной аутентификацией.\n"
            "Введите пароль 2FA:",
        )
        return

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


@router.message(Auth2FA.password)
async def acc_auth_2fa(message: Message, state: FSMContext):
    data = await state.get_data()
    acc_id = data["acc_id"]
    password = message.text.strip()
    await state.clear()

    from services.account_manager import sign_in_2fa
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))
    result = await sign_in_2fa(acc, password)

    if not result["ok"]:
        await message.answer(
            f"❌ Ошибка 2FA: {result['error']}",
            reply_markup=account_item_kb(acc_id),
        )
        return

    await execute("UPDATE accounts SET status = 'active' WHERE id = ?", (acc_id,))
    await message.answer(
        f"✅ Аккаунт успешно авторизован (2FA)!",
        reply_markup=account_item_kb(acc_id),
    )


# ============================================================
# Редактирование прокси
# ============================================================

@router.callback_query(F.data.startswith("acc_proxy_"))
async def acc_proxy_edit(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    await state.set_state(EditProxy.value)
    await state.update_data(acc_id=acc_id)
    await callback.message.edit_text(
        "🌐 Введите новый прокси:\n\n"
        "Форматы:\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>http://host:port</code>\n\n"
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
