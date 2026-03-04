from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    presets_menu_kb, preset_list_kb, preset_item_kb,
    prs_mode_kb, prs_tpl_select_kb, prs_select_items_kb,
    prs_limits_kb, prs_confirm_del_kb, back_kb, MODE_LABELS,
)

router = Router()


class AddPreset(StatesGroup):
    name = State()


class SetPresetLimit(StatesGroup):
    value = State()


# --- Меню ---

@router.callback_query(F.data.in_({"presets", "back_presets"}))
async def presets_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    count = await fetch_one("SELECT COUNT(*) as cnt FROM presets")
    text = (
        f"📦 <b>Пресеты</b>\n\n"
        f"Всего: {count['cnt']}\n\n"
        f"Пресет = готовый набор настроек для проекта:\n"
        f"шаблон профиля + сообщения + каналы + режим + лимиты.\n\n"
        f"Переключайте пресеты одной кнопкой!"
    )
    await callback.message.edit_text(
        text, reply_markup=presets_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "prs_list")
async def prs_list(callback: CallbackQuery):
    presets = await fetch_all("SELECT id, name FROM presets ORDER BY id")
    if not presets:
        await callback.answer("Список пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Пресеты:</b>",
        reply_markup=preset_list_kb(presets),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр ---

@router.callback_query(F.data.startswith("prs_view_"))
async def prs_view(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    prs = await fetch_one("SELECT * FROM presets WHERE id = ?", (prs_id,))
    if not prs:
        await callback.answer("Пресет не найден", show_alert=True)
        return

    ch_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM preset_channels WHERE preset_id = ?", (prs_id,))
    msg_count = await fetch_one(
        "SELECT COUNT(*) as cnt FROM preset_messages WHERE preset_id = ?", (prs_id,))

    mode = prs["mode"] or "comments"
    mode_labels = [MODE_LABELS.get(m, m) for m in mode.split(",")]
    mode_label = ", ".join(mode_labels)

    # Шаблон профиля
    tpl_name = "—"
    if prs["template_id"]:
        tpl = await fetch_one(
            "SELECT name FROM account_templates WHERE id = ?", (prs["template_id"],))
        if tpl:
            tpl_name = tpl["name"]

    # Статус кампании
    camp_status = "—"
    if prs["campaign_id"]:
        camp = await fetch_one(
            "SELECT is_active FROM campaigns WHERE id = ?", (prs["campaign_id"],))
        if camp:
            camp_status = "🟢 Активна" if camp["is_active"] else "🔴 Остановлена"

    text = (
        f"📦 <b>Пресет: {prs['name']}</b>\n\n"
        f"Кампания: {camp_status}\n"
        f"Режим: {mode_label}\n"
        f"Шаблон профиля: {tpl_name}\n"
        f"Каналов: {ch_count['cnt']}\n"
        f"Сообщений: {msg_count['cnt']}\n\n"
        f"⚙️ <b>Лимиты:</b>\n"
        f"Задержка: {prs['delay_min']}–{prs['delay_max']} сек\n"
        f"В час: {prs['hourly_limit']}\n"
        f"В день: {prs['daily_limit']}"
    )
    await callback.message.edit_text(
        text, reply_markup=preset_item_kb(prs_id), parse_mode="HTML")
    await callback.answer()


# --- Создание ---

@router.callback_query(F.data == "prs_add")
async def prs_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPreset.name)
    await callback.message.edit_text(
        "📦 Введите название пресета (например: «Крипто-проект», «Недвижимость»):",
        reply_markup=back_kb("presets"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddPreset.name)
async def prs_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым:")
        return
    await state.clear()
    prs_id = await execute_returning(
        "INSERT INTO presets (name) VALUES (?)", (name,))
    await message.answer(
        f"✅ Пресет «{name}» создан (#{prs_id}).\n\n"
        f"Теперь настройте: шаблон профиля, каналы, сообщения, режим и лимиты.",
        reply_markup=preset_item_kb(prs_id),
    )


# --- Активация ---

@router.callback_query(F.data.startswith("prs_activate_"))
async def prs_activate(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    prs = await fetch_one("SELECT name FROM presets WHERE id = ?", (prs_id,))
    if not prs:
        await callback.answer("Пресет не найден", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Активирую пресет «{prs['name']}»...\n\n"
        f"Настраиваю кампанию, профили аккаунтов...",
        parse_mode="HTML",
    )
    await callback.answer()

    from services.preset_manager import activate_preset
    result = await activate_preset(prs_id)

    if not result["ok"]:
        await callback.message.edit_text(
            f"❌ Ошибка: {result['error']}",
            reply_markup=preset_item_kb(prs_id),
        )
        return

    modes = result.get("modes", ["comments"])
    mode_labels = [MODE_LABELS.get(m, m) for m in modes]
    camp_ids = result.get("campaign_ids", [result["campaign_id"]])
    camps_str = ", ".join(f"#{c}" for c in camp_ids)

    text = (
        f"✅ <b>Пресет «{prs['name']}» активирован!</b>\n\n"
        f"🎯 Режимы: {', '.join(mode_labels)}\n"
        f"🚀 Кампании: {camps_str}\n"
        f"📢 Каналов: {result['channels']}\n"
        f"💬 Сообщений: {result['messages']}\n"
        f"📱 Аккаунтов: {result['accounts']}"
    )
    profile = result.get("profile", {})
    if profile.get("applied"):
        text += (
            f"\n\n👤 Профили обновлены: "
            f"{profile['success']} ✅ / {profile['errors']} ❌"
        )

    await callback.message.edit_text(
        text, reply_markup=preset_item_kb(prs_id), parse_mode="HTML")


# --- Шаблон профиля ---

@router.callback_query(F.data.startswith("prs_tpl_set_"))
async def prs_tpl_set(callback: CallbackQuery):
    parts = callback.data.split("_")
    prs_id = int(parts[3])
    tpl_id = int(parts[4])

    await execute(
        "UPDATE presets SET template_id = ? WHERE id = ?", (tpl_id, prs_id))
    await callback.answer("✅ Шаблон привязан")

    # Перерисовать список шаблонов
    templates = await fetch_all(
        "SELECT id, name FROM account_templates ORDER BY id")
    prs = await fetch_one("SELECT template_id FROM presets WHERE id = ?", (prs_id,))
    await callback.message.edit_reply_markup(
        reply_markup=prs_tpl_select_kb(templates, prs_id, prs["template_id"]))


@router.callback_query(F.data.startswith("prs_tpl_clear_"))
async def prs_tpl_clear(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[3])
    await execute(
        "UPDATE presets SET template_id = NULL WHERE id = ?", (prs_id,))
    await callback.answer("✅ Шаблон убран")

    templates = await fetch_all(
        "SELECT id, name FROM account_templates ORDER BY id")
    await callback.message.edit_reply_markup(
        reply_markup=prs_tpl_select_kb(templates, prs_id, None))


@router.callback_query(F.data.startswith("prs_tpl_"))
async def prs_tpl(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    templates = await fetch_all(
        "SELECT id, name FROM account_templates ORDER BY id")
    if not templates:
        await callback.answer(
            "Сначала создайте шаблон профиля (Аккаунты → Шаблоны)", show_alert=True)
        return

    prs = await fetch_one("SELECT template_id FROM presets WHERE id = ?", (prs_id,))
    await callback.message.edit_text(
        "👤 Выберите шаблон профиля для пресета:",
        reply_markup=prs_tpl_select_kb(templates, prs_id, prs["template_id"]),
    )
    await callback.answer()


# --- Режим ---

@router.callback_query(F.data.startswith("prs_setmode_"))
async def prs_setmode(callback: CallbackQuery):
    parts = callback.data.split("_")
    prs_id = int(parts[2])
    toggled_mode = "_".join(parts[3:])

    # Мультивыбор: переключаем режим вкл/выкл
    prs = await fetch_one("SELECT mode FROM presets WHERE id = ?", (prs_id,))
    current_modes = set((prs["mode"] or "comments").split(","))

    if toggled_mode in current_modes:
        current_modes.discard(toggled_mode)
    else:
        current_modes.add(toggled_mode)

    # Не допускаем пустой набор режимов
    if not current_modes:
        await callback.answer("Нужен хотя бы один режим", show_alert=True)
        return

    new_mode = ",".join(sorted(current_modes, key=lambda m: list(MODE_LABELS.keys()).index(m)
                                if m in MODE_LABELS else 99))
    await execute("UPDATE presets SET mode = ? WHERE id = ?", (new_mode, prs_id))

    labels = [MODE_LABELS.get(m, m) for m in new_mode.split(",")]
    await callback.answer(f"✅ Режимы: {', '.join(labels)}")

    await callback.message.edit_reply_markup(
        reply_markup=prs_mode_kb(prs_id, new_mode))


@router.callback_query(F.data.startswith("prs_mode_"))
async def prs_mode(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    prs = await fetch_one("SELECT * FROM presets WHERE id = ?", (prs_id,))
    if not prs:
        await callback.answer("Пресет не найден", show_alert=True)
        return

    current_mode = prs["mode"] or "comments"
    labels = [MODE_LABELS.get(m, m) for m in current_mode.split(",")]
    await callback.message.edit_text(
        f"🎯 <b>Режимы пресета «{prs['name']}»</b>\n\n"
        f"Выбрано: {', '.join(labels)}\n\n"
        f"Можно выбрать несколько режимов одновременно.",
        reply_markup=prs_mode_kb(prs_id, current_mode),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Каналы ---

@router.callback_query(F.data.startswith("prs_channels_"))
async def prs_channels(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    channels = await fetch_all("SELECT id, username FROM channels ORDER BY id")
    linked = await fetch_all(
        "SELECT channel_id FROM preset_channels WHERE preset_id = ?", (prs_id,))
    selected_ids = {r["channel_id"] for r in linked}

    if not channels:
        await callback.answer("Сначала добавьте каналы", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 Выберите каналы для пресета:",
        reply_markup=prs_select_items_kb(channels, "prs_ch", prs_id, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prs_ch_toggle_"))
async def prs_ch_toggle(callback: CallbackQuery):
    parts = callback.data.split("_")
    prs_id = int(parts[3])
    ch_id = int(parts[4])

    existing = await fetch_one(
        "SELECT 1 FROM preset_channels WHERE preset_id = ? AND channel_id = ?",
        (prs_id, ch_id))
    if existing:
        await execute(
            "DELETE FROM preset_channels WHERE preset_id = ? AND channel_id = ?",
            (prs_id, ch_id))
    else:
        await execute(
            "INSERT INTO preset_channels (preset_id, channel_id) VALUES (?, ?)",
            (prs_id, ch_id))

    channels = await fetch_all("SELECT id, username FROM channels ORDER BY id")
    linked = await fetch_all(
        "SELECT channel_id FROM preset_channels WHERE preset_id = ?", (prs_id,))
    selected_ids = {r["channel_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=prs_select_items_kb(channels, "prs_ch", prs_id, selected_ids))
    await callback.answer()


# --- Сообщения ---

@router.callback_query(F.data.startswith("prs_messages_"))
async def prs_messages(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    messages = await fetch_all(
        "SELECT id, text FROM messages WHERE is_active = 1 ORDER BY id")
    linked = await fetch_all(
        "SELECT message_id FROM preset_messages WHERE preset_id = ?", (prs_id,))
    selected_ids = {r["message_id"] for r in linked}

    if not messages:
        await callback.answer("Сначала добавьте сообщения", show_alert=True)
        return

    await callback.message.edit_text(
        "💬 Выберите сообщения для пресета:",
        reply_markup=prs_select_items_kb(messages, "prs_msg", prs_id, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prs_msg_toggle_"))
async def prs_msg_toggle(callback: CallbackQuery):
    parts = callback.data.split("_")
    prs_id = int(parts[3])
    msg_id = int(parts[4])

    existing = await fetch_one(
        "SELECT 1 FROM preset_messages WHERE preset_id = ? AND message_id = ?",
        (prs_id, msg_id))
    if existing:
        await execute(
            "DELETE FROM preset_messages WHERE preset_id = ? AND message_id = ?",
            (prs_id, msg_id))
    else:
        await execute(
            "INSERT INTO preset_messages (preset_id, message_id) VALUES (?, ?)",
            (prs_id, msg_id))

    messages = await fetch_all(
        "SELECT id, text FROM messages WHERE is_active = 1 ORDER BY id")
    linked = await fetch_all(
        "SELECT message_id FROM preset_messages WHERE preset_id = ?", (prs_id,))
    selected_ids = {r["message_id"] for r in linked}

    await callback.message.edit_reply_markup(
        reply_markup=prs_select_items_kb(messages, "prs_msg", prs_id, selected_ids))
    await callback.answer()


# --- Лимиты ---

@router.callback_query(F.data.startswith("prs_limits_"))
async def prs_limits(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    prs = await fetch_one("SELECT * FROM presets WHERE id = ?", (prs_id,))
    text = (
        f"⚙️ <b>Лимиты пресета «{prs['name']}»</b>\n\n"
        f"⏱ Мин. задержка: {prs['delay_min']} сек\n"
        f"⏱ Макс. задержка: {prs['delay_max']} сек\n"
        f"🕐 Лимит/час: {prs['hourly_limit']}\n"
        f"📅 Лимит/день: {prs['daily_limit']}"
    )
    await callback.message.edit_text(
        text, reply_markup=prs_limits_kb(prs_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("prs_set_"))
async def prs_set_limit(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    prs_id = int(parts[-1])
    field = "_".join(parts[2:-1])

    field_map = {
        "delay_min": ("delay_min", "минимальную задержку (сек)"),
        "delay_max": ("delay_max", "максимальную задержку (сек)"),
        "hourly": ("hourly_limit", "лимит в час"),
        "daily": ("daily_limit", "лимит в день"),
    }
    db_field, label = field_map[field]

    await state.set_state(SetPresetLimit.value)
    await state.update_data(prs_id=prs_id, db_field=db_field)
    await callback.message.edit_text(f"✏️ Введите {label}:")
    await callback.answer()


@router.message(SetPresetLimit.value)
async def prs_set_limit_value(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите число:")
        return
    value = int(message.text.strip())
    data = await state.get_data()
    await state.clear()

    await execute(
        f"UPDATE presets SET {data['db_field']} = ? WHERE id = ?",
        (value, data["prs_id"]),
    )
    await message.answer(
        f"✅ Значение обновлено.",
        reply_markup=prs_limits_kb(data["prs_id"]),
    )


# --- Удаление ---

@router.callback_query(F.data.startswith("prs_del_confirm_"))
async def prs_del_confirm(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[3])
    await execute("DELETE FROM preset_channels WHERE preset_id = ?", (prs_id,))
    await execute("DELETE FROM preset_messages WHERE preset_id = ?", (prs_id,))
    await execute("DELETE FROM presets WHERE id = ?", (prs_id,))
    await callback.message.edit_text(
        "✅ Пресет удалён.", reply_markup=presets_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("prs_del_"))
async def prs_del(callback: CallbackQuery):
    prs_id = int(callback.data.split("_")[2])
    prs = await fetch_one("SELECT name FROM presets WHERE id = ?", (prs_id,))
    if not prs:
        await callback.answer("Пресет не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑 Удалить пресет «{prs['name']}»?\n\n"
        f"Связанная кампания <b>не будет</b> удалена.",
        reply_markup=prs_confirm_del_kb(prs_id),
        parse_mode="HTML",
    )
    await callback.answer()
