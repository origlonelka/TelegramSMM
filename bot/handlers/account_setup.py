import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    acc_setup_menu_kb, tpl_list_kb, tpl_item_kb,
    tpl_confirm_del_kb, tpl_select_acc_kb, back_kb,
)

router = Router()

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)


# --- FSM States ---

class AddTemplate(StatesGroup):
    name = State()
    first_name = State()
    last_name = State()
    bio = State()
    photo = State()


# --- Меню шаблонов ---

@router.callback_query(F.data.in_({"acc_setup", "back_acc_setup"}))
async def acc_setup_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    count = await fetch_one("SELECT COUNT(*) as cnt FROM account_templates")
    text = (
        f"👤 <b>Шаблоны профиля</b>\n\n"
        f"Всего: {count['cnt']}\n\n"
        f"Создайте шаблон с именем, фамилией, bio и фото.\n"
        f"Все поля поддерживают spintax: <code>{{Имя1|Имя2|Имя3}}</code>"
    )
    await callback.message.edit_text(
        text, reply_markup=acc_setup_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "tpl_list")
async def tpl_list(callback: CallbackQuery):
    templates = await fetch_all(
        "SELECT id, name FROM account_templates ORDER BY id")
    if not templates:
        await callback.answer("Список пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Шаблоны профиля:</b>",
        reply_markup=tpl_list_kb(templates),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр ---

@router.callback_query(F.data.startswith("tpl_view_"))
async def tpl_view(callback: CallbackQuery):
    tpl_id = int(callback.data.split("_")[2])
    tpl = await fetch_one(
        "SELECT * FROM account_templates WHERE id = ?", (tpl_id,))
    if not tpl:
        await callback.answer("Шаблон не найден", show_alert=True)
        return

    first_name = tpl["first_name"] or "—"
    last_name = tpl["last_name"] or "—"
    bio = tpl["bio"] or "—"
    photo = "✅ Есть" if tpl["photo_path"] and os.path.exists(tpl["photo_path"]) else "❌ Нет"

    text = (
        f"👤 <b>Шаблон: {tpl['name']}</b>\n\n"
        f"Имя: <code>{first_name}</code>\n"
        f"Фамилия: <code>{last_name}</code>\n"
        f"Bio: <code>{bio}</code>\n"
        f"Фото: {photo}\n\n"
        f"💡 Spintax в полях раскрывается случайно для каждого аккаунта."
    )
    await callback.message.edit_text(
        text, reply_markup=tpl_item_kb(tpl_id), parse_mode="HTML")
    await callback.answer()


# --- Создание шаблона ---

@router.callback_query(F.data == "tpl_add")
async def tpl_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTemplate.name)
    await callback.message.edit_text(
        "👤 <b>Создание шаблона профиля</b>\n\n"
        "Введите название шаблона (для себя):",
        reply_markup=back_kb("acc_setup"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddTemplate.name)
async def tpl_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым:")
        return
    await state.update_data(name=name)
    await state.set_state(AddTemplate.first_name)
    await message.answer(
        "📝 Введите <b>имя</b> для аккаунтов:\n\n"
        "Поддерживает spintax: <code>{Алексей|Дмитрий|Иван}</code>\n\n"
        "Отправьте <b>-</b> чтобы не менять имя.",
        parse_mode="HTML",
    )


@router.message(AddTemplate.first_name)
async def tpl_add_first_name(message: Message, state: FSMContext):
    text = message.text.strip()
    first_name = None if text == "-" else text
    await state.update_data(first_name=first_name)
    await state.set_state(AddTemplate.last_name)
    await message.answer(
        "📝 Введите <b>фамилию</b>:\n\n"
        "Spintax: <code>{Петров|Иванов|Козлов}</code>\n\n"
        "Отправьте <b>-</b> чтобы оставить пустой.",
        parse_mode="HTML",
    )


@router.message(AddTemplate.last_name)
async def tpl_add_last_name(message: Message, state: FSMContext):
    text = message.text.strip()
    last_name = None if text == "-" else text
    await state.update_data(last_name=last_name)
    await state.set_state(AddTemplate.bio)
    await message.answer(
        "📝 Введите <b>bio</b> (описание профиля):\n\n"
        "Spintax: <code>{Бизнесмен|Инвестор} из {Москвы|СПб}</code>\n\n"
        "Отправьте <b>-</b> чтобы оставить пустым.",
        parse_mode="HTML",
    )


@router.message(AddTemplate.bio)
async def tpl_add_bio(message: Message, state: FSMContext):
    text = message.text.strip()
    bio = None if text == "-" else text
    await state.update_data(bio=bio)
    await state.set_state(AddTemplate.photo)
    await message.answer(
        "📷 Отправьте <b>фото</b> для аватарки аккаунтов.\n\n"
        "Отправьте <b>-</b> чтобы пропустить.",
        parse_mode="HTML",
    )


@router.message(AddTemplate.photo, F.photo)
async def tpl_add_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    # Создаём шаблон в БД
    tpl_id = await execute_returning(
        "INSERT INTO account_templates (name, first_name, last_name, bio) VALUES (?, ?, ?, ?)",
        (data["name"], data.get("first_name"), data.get("last_name"), data.get("bio")),
    )

    # Скачиваем фото
    photo = message.photo[-1]  # Максимальное разрешение
    photo_path = os.path.join(TEMPLATES_DIR, f"photo_{tpl_id}.jpg")
    await message.bot.download(photo.file_id, destination=photo_path)

    await execute(
        "UPDATE account_templates SET photo_path = ? WHERE id = ?",
        (photo_path, tpl_id),
    )

    await message.answer(
        f"✅ Шаблон «{data['name']}» создан (#{tpl_id})!",
        reply_markup=tpl_item_kb(tpl_id),
    )


@router.message(AddTemplate.photo)
async def tpl_add_photo_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    tpl_id = await execute_returning(
        "INSERT INTO account_templates (name, first_name, last_name, bio) VALUES (?, ?, ?, ?)",
        (data["name"], data.get("first_name"), data.get("last_name"), data.get("bio")),
    )

    await message.answer(
        f"✅ Шаблон «{data['name']}» создан (#{tpl_id})!",
        reply_markup=tpl_item_kb(tpl_id),
    )


# --- Применение шаблона ---

@router.callback_query(F.data.startswith("tpl_apply_all_"))
async def tpl_apply_all(callback: CallbackQuery):
    tpl_id = int(callback.data.split("_")[3])
    tpl = await fetch_one(
        "SELECT * FROM account_templates WHERE id = ?", (tpl_id,))
    if not tpl:
        await callback.answer("Шаблон не найден", show_alert=True)
        return

    accounts = await fetch_all(
        "SELECT * FROM accounts WHERE status = 'active'")
    if not accounts:
        await callback.answer("Нет активных аккаунтов", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Применяю шаблон «{tpl['name']}» к {len(accounts)} аккаунтам...",
        parse_mode="HTML",
    )
    await callback.answer()

    from services.account_setup import apply_template
    success = 0
    errors = 0
    for acc in accounts:
        result = await apply_template(acc, tpl)
        if result["ok"]:
            success += 1
        else:
            errors += 1

    text = f"✅ Шаблон применён!\n\nУспешно: {success}"
    if errors:
        text += f"\nОшибки: {errors}"
    await callback.message.edit_text(
        text, reply_markup=tpl_item_kb(tpl_id))


@router.callback_query(F.data.startswith("tpl_apply_pick_"))
async def tpl_apply_pick(callback: CallbackQuery):
    tpl_id = int(callback.data.split("_")[3])
    accounts = await fetch_all(
        "SELECT id, phone FROM accounts WHERE status = 'active' ORDER BY id")
    if not accounts:
        await callback.answer("Нет активных аккаунтов", show_alert=True)
        return

    await callback.message.edit_text(
        "📱 Выберите аккаунт для применения шаблона:",
        reply_markup=tpl_select_acc_kb(accounts, tpl_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tpl_apply_"))
async def tpl_apply_single(callback: CallbackQuery):
    parts = callback.data.split("_")
    # tpl_apply_{tpl_id}_{acc_id}
    tpl_id = int(parts[2])
    acc_id = int(parts[3])

    tpl = await fetch_one(
        "SELECT * FROM account_templates WHERE id = ?", (tpl_id,))
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))

    if not tpl or not acc:
        await callback.answer("Не найдено", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Применяю шаблон «{tpl['name']}» к {acc['phone']}...")
    await callback.answer()

    from services.account_setup import apply_template
    result = await apply_template(acc, tpl)

    if result["ok"]:
        text = (
            f"✅ Шаблон применён к {acc['phone']}!\n\n"
            f"Имя: {result.get('first_name', '—')}\n"
            f"Фамилия: {result.get('last_name', '—')}"
        )
    else:
        text = f"❌ Ошибка: {result['error']}"

    await callback.message.edit_text(
        text, reply_markup=tpl_item_kb(tpl_id))


# --- Удаление ---

@router.callback_query(F.data.startswith("tpl_del_confirm_"))
async def tpl_del_confirm(callback: CallbackQuery):
    tpl_id = int(callback.data.split("_")[3])

    # Удаляем фото если есть
    tpl = await fetch_one(
        "SELECT photo_path FROM account_templates WHERE id = ?", (tpl_id,))
    if tpl and tpl["photo_path"] and os.path.exists(tpl["photo_path"]):
        os.remove(tpl["photo_path"])

    await execute("DELETE FROM account_templates WHERE id = ?", (tpl_id,))
    await callback.message.edit_text(
        "✅ Шаблон удалён.", reply_markup=acc_setup_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("tpl_del_"))
async def tpl_del(callback: CallbackQuery):
    tpl_id = int(callback.data.split("_")[2])
    tpl = await fetch_one(
        "SELECT name FROM account_templates WHERE id = ?", (tpl_id,))
    await callback.message.edit_text(
        f"🗑 Удалить шаблон «{tpl['name']}»?",
        reply_markup=tpl_confirm_del_kb(tpl_id),
    )
    await callback.answer()
