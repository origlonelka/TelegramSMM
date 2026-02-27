from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Аккаунты", callback_data="accounts"),
         InlineKeyboardButton(text="📢 Каналы", callback_data="channels")],
        [InlineKeyboardButton(text="💬 Сообщения", callback_data="messages"),
         InlineKeyboardButton(text="🚀 Кампании", callback_data="campaigns")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    ])


def back_kb(to: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_{to}")],
    ])


# --- Аккаунты ---

def accounts_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="acc_add")],
        [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="acc_list")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def acc_add_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Телефон + SMS", callback_data="acc_add_phone")],
        [InlineKeyboardButton(text="⚡ Быстрое (API из .env)", callback_data="acc_add_quick")],
        [InlineKeyboardButton(text="📋 Session string", callback_data="acc_add_session")],
        [InlineKeyboardButton(text="📁 Session файл (.session)", callback_data="acc_add_file")],
        [InlineKeyboardButton(text="📂 Tdata (ZIP архив)", callback_data="acc_add_tdata")],
        [InlineKeyboardButton(text="◀️ К аккаунтам", callback_data="accounts")],
    ])


def account_item_kb(acc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Авторизовать", callback_data=f"acc_auth_{acc_id}"),
         InlineKeyboardButton(text="🌐 Прокси", callback_data=f"acc_proxy_{acc_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"acc_del_{acc_id}")],
        [InlineKeyboardButton(text="◀️ К аккаунтам", callback_data="accounts")],
    ])


def account_list_kb(accounts: list) -> InlineKeyboardMarkup:
    buttons = []
    for acc in accounts:
        status_icon = "🟢" if acc["status"] == "active" else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{status_icon} {acc['phone']}",
            callback_data=f"acc_view_{acc['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К аккаунтам", callback_data="accounts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def acc_confirm_del_kb(acc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"acc_del_confirm_{acc_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"acc_view_{acc_id}")],
    ])


# --- Каналы ---

def channels_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="ch_add")],
        [InlineKeyboardButton(text="🔍 Поиск каналов", callback_data="ch_search")],
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="ch_list")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def channel_list_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        comments_icon = "💬" if ch["has_comments"] else "🔇"
        buttons.append([InlineKeyboardButton(
            text=f"{comments_icon} @{ch['username']} — {ch['title'] or 'Без названия'}",
            callback_data=f"ch_view_{ch['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К каналам", callback_data="channels")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channel_item_kb(ch_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ch_del_{ch_id}")],
        [InlineKeyboardButton(text="◀️ К каналам", callback_data="channels")],
    ])


def ch_confirm_del_kb(ch_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"ch_del_confirm_{ch_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"ch_view_{ch_id}")],
    ])


def ch_search_results_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"➕ @{ch['username']} — {ch['title']}",
            callback_data=f"ch_search_add_{ch['username']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К каналам", callback_data="channels")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Сообщения ---

def messages_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить сообщение", callback_data="msg_add")],
        [InlineKeyboardButton(text="📋 Список сообщений", callback_data="msg_list")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def message_list_kb(messages: list) -> InlineKeyboardMarkup:
    buttons = []
    for msg in messages:
        status_icon = "🟢" if msg["is_active"] else "🔴"
        preview = msg["text"][:40] + "..." if len(msg["text"]) > 40 else msg["text"]
        buttons.append([InlineKeyboardButton(
            text=f"{status_icon} {preview}",
            callback_data=f"msg_view_{msg['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К сообщениям", callback_data="messages")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def message_item_kb(msg_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить" if is_active else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"msg_toggle_{msg_id}"),
         InlineKeyboardButton(text="🗑 Удалить", callback_data=f"msg_del_{msg_id}")],
        [InlineKeyboardButton(text="◀️ К сообщениям", callback_data="messages")],
    ])


def msg_confirm_del_kb(msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"msg_del_confirm_{msg_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"msg_view_{msg_id}")],
    ])


# --- Кампании ---

def campaigns_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать кампанию", callback_data="camp_add")],
        [InlineKeyboardButton(text="📋 Список кампаний", callback_data="camp_list")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def campaign_list_kb(campaigns: list) -> InlineKeyboardMarkup:
    buttons = []
    for camp in campaigns:
        status_icon = "🟢" if camp["is_active"] else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{status_icon} {camp['name']}",
            callback_data=f"camp_view_{camp['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К кампаниям", callback_data="campaigns")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def campaign_item_kb(camp_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⏸ Остановить" if is_active else "▶️ Запустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"camp_toggle_{camp_id}")],
        [InlineKeyboardButton(text="📢 Каналы", callback_data=f"camp_channels_{camp_id}"),
         InlineKeyboardButton(text="📱 Аккаунты", callback_data=f"camp_accounts_{camp_id}")],
        [InlineKeyboardButton(text="💬 Сообщения", callback_data=f"camp_messages_{camp_id}"),
         InlineKeyboardButton(text="⚙️ Лимиты", callback_data=f"camp_limits_{camp_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"camp_del_{camp_id}")],
        [InlineKeyboardButton(text="◀️ К кампаниям", callback_data="campaigns")],
    ])


def camp_confirm_del_kb(camp_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"camp_del_confirm_{camp_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"camp_view_{camp_id}")],
    ])


def camp_select_items_kb(items: list, prefix: str, camp_id: int, selected_ids: set) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        d = dict(item)
        check = "✅" if d["id"] in selected_ids else "⬜"
        label = d.get("phone") or d.get("username") or d.get("text", "")[:30]
        buttons.append([InlineKeyboardButton(
            text=f"{check} {label}",
            callback_data=f"{prefix}_toggle_{camp_id}_{d['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="💾 Сохранить", callback_data=f"camp_view_{camp_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def camp_limits_kb(camp_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ Мин. задержка", callback_data=f"camp_set_delay_min_{camp_id}"),
         InlineKeyboardButton(text="⏱ Макс. задержка", callback_data=f"camp_set_delay_max_{camp_id}")],
        [InlineKeyboardButton(text="🕐 Лимит/час", callback_data=f"camp_set_hourly_{camp_id}"),
         InlineKeyboardButton(text="📅 Лимит/день", callback_data=f"camp_set_daily_{camp_id}")],
        [InlineKeyboardButton(text="◀️ К кампании", callback_data=f"camp_view_{camp_id}")],
    ])


# --- Настройки ---

def settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 API настройки", callback_data="settings_api")],
        [InlineKeyboardButton(text="🔄 Сбросить лимиты", callback_data="settings_reset_limits")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


# --- Статистика ---

def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])
