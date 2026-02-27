from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import execute, execute_returning, fetch_all, fetch_one
from bot.keyboards.inline import (
    channels_menu_kb, channel_list_kb, channel_item_kb,
    ch_confirm_del_kb, ch_search_results_kb, back_kb,
)

router = Router()


class AddChannel(StatesGroup):
    username = State()


class SearchChannel(StatesGroup):
    keyword = State()


# --- Меню каналов ---

@router.callback_query(F.data.in_({"channels", "back_channels"}))
async def channels_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    count = await fetch_one("SELECT COUNT(*) as cnt FROM channels")
    text = f"📢 <b>Каналы</b>\n\nВсего: {count['cnt']}"
    await callback.message.edit_text(text, reply_markup=channels_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Список ---

@router.callback_query(F.data == "ch_list")
async def ch_list(callback: CallbackQuery):
    channels = await fetch_all("SELECT id, username, title, has_comments FROM channels ORDER BY id")
    if not channels:
        await callback.answer("Список пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Список каналов:</b>",
        reply_markup=channel_list_kb(channels),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр ---

@router.callback_query(F.data.startswith("ch_view_"))
async def ch_view(callback: CallbackQuery):
    ch_id = int(callback.data.split("_")[2])
    ch = await fetch_one("SELECT * FROM channels WHERE id = ?", (ch_id,))
    if not ch:
        await callback.answer("Канал не найден", show_alert=True)
        return
    comments_status = "💬 Открыты" if ch["has_comments"] else "🔇 Закрыты"
    text = (
        f"📢 <b>Канал #{ch['id']}</b>\n\n"
        f"Username: @{ch['username']}\n"
        f"Название: {ch['title'] or '—'}\n"
        f"Комментарии: {comments_status}\n"
        f"Добавлен: {ch['added_at']}"
    )
    await callback.message.edit_text(text, reply_markup=channel_item_kb(ch_id), parse_mode="HTML")
    await callback.answer()


# --- Добавление вручную ---

@router.callback_query(F.data == "ch_add")
async def ch_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.username)
    await callback.message.edit_text(
        "📢 Введите @username канала (без @):",
        reply_markup=back_kb("channels"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddChannel.username)
async def ch_add_username(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    await state.clear()

    existing = await fetch_one("SELECT id FROM channels WHERE username = ?", (username,))
    if existing:
        await message.answer("❌ Канал уже добавлен.")
        return

    ch_id = await execute_returning(
        "INSERT INTO channels (username) VALUES (?)", (username,)
    )
    await message.answer(
        f"✅ Канал @{username} добавлен (#{ch_id}).",
        reply_markup=channel_item_kb(ch_id),
    )


# --- Поиск ---

@router.callback_query(F.data == "ch_search")
async def ch_search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchChannel.keyword)
    await callback.message.edit_text(
        "🔍 Введите ключевое слово для поиска каналов (например: Hytale):",
        reply_markup=back_kb("channels"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SearchChannel.keyword)
async def ch_search_keyword(message: Message, state: FSMContext):
    keyword = message.text.strip()
    await state.clear()

    from services.channel_parser import search_channels
    results = await search_channels(keyword)

    if not results:
        await message.answer("😕 Ничего не найдено. Попробуйте другой запрос.",
                             reply_markup=channels_menu_kb())
        return

    await message.answer(
        f"🔍 Найдено каналов: {len(results)}\nНажмите чтобы добавить:",
        reply_markup=ch_search_results_kb(results),
    )


@router.callback_query(F.data.startswith("ch_search_add_"))
async def ch_search_add(callback: CallbackQuery):
    username = callback.data.replace("ch_search_add_", "")
    existing = await fetch_one("SELECT id FROM channels WHERE username = ?", (username,))
    if existing:
        await callback.answer("Канал уже добавлен", show_alert=True)
        return
    await execute_returning(
        "INSERT INTO channels (username) VALUES (?)", (username,)
    )
    await callback.answer(f"✅ @{username} добавлен!", show_alert=True)


# --- Удаление ---

@router.callback_query(F.data.startswith("ch_del_confirm_"))
async def ch_del_confirm(callback: CallbackQuery):
    ch_id = int(callback.data.split("_")[3])
    await execute("DELETE FROM channels WHERE id = ?", (ch_id,))
    await callback.message.edit_text("✅ Канал удалён.", reply_markup=channels_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("ch_del_"))
async def ch_del(callback: CallbackQuery):
    ch_id = int(callback.data.split("_")[2])
    ch = await fetch_one("SELECT username FROM channels WHERE id = ?", (ch_id,))
    await callback.message.edit_text(
        f"🗑 Удалить канал @{ch['username']}?",
        reply_markup=ch_confirm_del_kb(ch_id),
    )
    await callback.answer()
