from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import fetch_all, fetch_one
from bot.keyboards.inline import (
    proxy_pool_menu_kb, proxy_list_kb, proxy_item_kb, back_kb,
)

router = Router()


class ImportProxies(StatesGroup):
    text = State()


# --- Меню ---

@router.callback_query(F.data.in_({"proxy_pool", "back_proxy_pool"}))
async def proxy_pool_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from services.proxy_manager import get_pool_stats
    stats = await get_pool_stats()

    text = (
        f"🌐 <b>Прокси-пул</b>\n\n"
        f"Всего: {stats['total']}\n"
        f"🟢 Живых: {stats['alive']}\n"
        f"🔴 Мёртвых: {stats['dead']}\n"
        f"⚪ Не проверено: {stats['unchecked']}\n\n"
        f"📱 Назначено: {stats['assigned']}\n"
        f"🆓 Свободных: {stats['free']}"
    )
    await callback.message.edit_text(
        text, reply_markup=proxy_pool_menu_kb(), parse_mode="HTML")
    await callback.answer()


# --- Импорт ---

@router.callback_query(F.data == "prx_import")
async def prx_import_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ImportProxies.text)
    await callback.message.edit_text(
        "🌐 <b>Импорт прокси</b>\n\n"
        "Отправьте список прокси (по одной на строку).\n\n"
        "Поддерживаемые форматы:\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>http://host:port</code>\n"
        "<code>host:port:user:pass</code>\n"
        "<code>host:port</code>\n\n"
        "Можно вставлять сразу много строк.",
        reply_markup=back_kb("proxy_pool"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ImportProxies.text)
async def prx_import_text(message: Message, state: FSMContext):
    text = message.text
    if not text or not text.strip():
        await message.answer("❌ Отправьте текст со списком прокси.")
        return
    await state.clear()

    from services.proxy_manager import import_proxies
    result = await import_proxies(text)

    reply = f"✅ Импорт завершён!\n\n➕ Добавлено: {result['added']}"
    if result["skipped"]:
        reply += f"\n⏭ Пропущено (дубли): {result['skipped']}"
    if result["errors"]:
        reply += f"\n❌ Ошибок парсинга: {result['errors']}"

    await message.answer(reply, reply_markup=proxy_pool_menu_kb())


# --- Список ---

@router.callback_query(F.data == "prx_list")
async def prx_list(callback: CallbackQuery):
    proxies = await fetch_all(
        "SELECT id, url, status, account_id FROM proxies ORDER BY status, id")
    if not proxies:
        await callback.answer("Пул пуст", show_alert=True)
        return
    await callback.message.edit_text(
        "📋 <b>Прокси в пуле:</b>",
        reply_markup=proxy_list_kb(proxies),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Просмотр ---

@router.callback_query(F.data.startswith("prx_view_"))
async def prx_view(callback: CallbackQuery):
    prx_id = int(callback.data.split("_")[2])
    proxy = await fetch_one("SELECT * FROM proxies WHERE id = ?", (prx_id,))
    if not proxy:
        await callback.answer("Прокси не найден", show_alert=True)
        return

    status_map = {
        "alive": "🟢 Живой",
        "dead": "🔴 Мёртвый",
        "unchecked": "⚪ Не проверен",
    }
    status = status_map.get(proxy["status"], proxy["status"])

    acc_info = "—"
    if proxy["account_id"]:
        acc = await fetch_one(
            "SELECT phone FROM accounts WHERE id = ?", (proxy["account_id"],))
        if acc:
            acc_info = f"📱 {acc['phone']}"

    ping = f"{proxy['response_time']} мс" if proxy["response_time"] else "—"
    checked = proxy["last_checked_at"] or "—"

    text = (
        f"🌐 <b>Прокси #{proxy['id']}</b>\n\n"
        f"URL: <code>{proxy['url']}</code>\n"
        f"Тип: {proxy['type']}\n"
        f"Статус: {status}\n"
        f"Пинг: {ping}\n"
        f"Аккаунт: {acc_info}\n"
        f"Проверен: {checked}\n"
        f"Добавлен: {proxy['added_at']}"
    )
    await callback.message.edit_text(
        text, reply_markup=proxy_item_kb(prx_id), parse_mode="HTML")
    await callback.answer()


# --- Проверить все ---

@router.callback_query(F.data == "prx_check_all")
async def prx_check_all(callback: CallbackQuery):
    total = await fetch_one("SELECT COUNT(*) as cnt FROM proxies")
    if total["cnt"] == 0:
        await callback.answer("Пул пуст", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Проверяю {total['cnt']} прокси...\nЭто может занять некоторое время.",
        parse_mode="HTML",
    )
    await callback.answer()

    from services.proxy_manager import check_all_proxies
    result = await check_all_proxies()

    await callback.message.edit_text(
        f"✅ <b>Проверка завершена</b>\n\n"
        f"🟢 Живых: {result['alive']}\n"
        f"🔴 Мёртвых: {result['dead']}\n"
        f"Всего: {result['total']}",
        reply_markup=proxy_pool_menu_kb(),
        parse_mode="HTML",
    )


# --- Проверка одного ---

@router.callback_query(F.data.startswith("prx_check_"))
async def prx_check(callback: CallbackQuery):
    prx_id = int(callback.data.split("_")[2])
    await callback.answer("⏳ Проверяю...")

    from services.proxy_manager import check_proxy
    result = await check_proxy(prx_id)

    proxy = await fetch_one("SELECT * FROM proxies WHERE id = ?", (prx_id,))
    if result["ok"]:
        await callback.message.edit_text(
            f"🟢 Прокси #{prx_id} — живой ({result['response_time']} мс)",
            reply_markup=proxy_item_kb(prx_id),
        )
    else:
        await callback.message.edit_text(
            f"🔴 Прокси #{prx_id} — мёртв\n\n<code>{result['error'][:200]}</code>",
            reply_markup=proxy_item_kb(prx_id),
            parse_mode="HTML",
        )


# --- Автоназначение ---

@router.callback_query(F.data == "prx_auto_assign")
async def prx_auto_assign(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Назначаю прокси аккаунтам...")
    await callback.answer()

    from services.proxy_manager import auto_assign_all
    result = await auto_assign_all()

    text = f"✅ Назначено: {result['assigned']}"
    if result["remaining"]:
        text += f"\n⚠️ Без прокси осталось: {result['remaining']}"
    if result["total"] == 0:
        text = "ℹ️ Все аккаунты уже с прокси."

    await callback.message.edit_text(
        text, reply_markup=proxy_pool_menu_kb())


# --- Ротация ---

@router.callback_query(F.data == "prx_rotate")
async def prx_rotate(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Ротирую мёртвые прокси...")
    await callback.answer()

    from services.proxy_manager import rotate_dead_proxies
    result = await rotate_dead_proxies()

    if result["rotated"] == 0 and result["failed"] == 0:
        text = "ℹ️ Нет мёртвых прокси для ротации."
    else:
        text = f"✅ Ротировано: {result['rotated']}"
        if result["failed"]:
            text += f"\n⚠️ Не удалось заменить: {result['failed']}"

    await callback.message.edit_text(
        text, reply_markup=proxy_pool_menu_kb())


# --- Снять прокси со всех аккаунтов ---

@router.callback_query(F.data == "prx_clear_all")
async def prx_clear_all(callback: CallbackQuery):
    from services.proxy_manager import clear_all_account_proxies
    count = await clear_all_account_proxies()

    if count == 0:
        await callback.answer("Ни у одного аккаунта нет прокси", show_alert=True)
    else:
        await callback.answer(f"🚫 Прокси сняты с {count} аккаунтов", show_alert=True)

    from services.proxy_manager import get_pool_stats
    stats = await get_pool_stats()
    text = (
        f"🌐 <b>Прокси-пул</b>\n\n"
        f"Всего: {stats['total']}\n"
        f"🟢 Живых: {stats['alive']}\n"
        f"🔴 Мёртвых: {stats['dead']}\n"
        f"⚪ Не проверено: {stats['unchecked']}\n\n"
        f"📱 Назначено: {stats['assigned']}\n"
        f"🆓 Свободных: {stats['free']}"
    )
    await callback.message.edit_text(
        text, reply_markup=proxy_pool_menu_kb(), parse_mode="HTML")


# --- Удалить мёртвые ---

@router.callback_query(F.data == "prx_del_dead")
async def prx_del_dead(callback: CallbackQuery):
    from services.proxy_manager import delete_dead_proxies
    count = await delete_dead_proxies()

    if count == 0:
        await callback.answer("Нет мёртвых прокси", show_alert=True)
    else:
        await callback.answer(f"🗑 Удалено мёртвых: {count}", show_alert=True)

    # Обновляем меню
    from services.proxy_manager import get_pool_stats
    stats = await get_pool_stats()
    text = (
        f"🌐 <b>Прокси-пул</b>\n\n"
        f"Всего: {stats['total']}\n"
        f"🟢 Живых: {stats['alive']}\n"
        f"🔴 Мёртвых: {stats['dead']}\n"
        f"⚪ Не проверено: {stats['unchecked']}\n\n"
        f"📱 Назначено: {stats['assigned']}\n"
        f"🆓 Свободных: {stats['free']}"
    )
    await callback.message.edit_text(
        text, reply_markup=proxy_pool_menu_kb(), parse_mode="HTML")


# --- Удалить одну ---

@router.callback_query(F.data.startswith("prx_del_confirm_"))
async def prx_del_confirm(callback: CallbackQuery):
    prx_id = int(callback.data.split("_")[3])
    from services.proxy_manager import delete_proxy
    await delete_proxy(prx_id)
    await callback.message.edit_text(
        "✅ Прокси удалён.", reply_markup=proxy_pool_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("prx_del_"))
async def prx_del(callback: CallbackQuery):
    prx_id = int(callback.data.split("_")[2])
    from bot.keyboards.inline import prx_confirm_del_kb
    await callback.message.edit_text(
        "🗑 Удалить этот прокси?",
        reply_markup=prx_confirm_del_kb(prx_id),
    )
    await callback.answer()
