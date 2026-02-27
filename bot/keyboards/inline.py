from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Аккаунты", callback_data="accounts"),
         InlineKeyboardButton(text="📢 Каналы", callback_data="channels")],
        [InlineKeyboardButton(text="💬 Сообщения", callback_data="messages"),
         InlineKeyboardButton(text="🚀 Кампании", callback_data="campaigns")],
        [InlineKeyboardButton(text="📦 Пресеты", callback_data="presets")],
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
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="acc_add"),
         InlineKeyboardButton(text="🤖 Авторег", callback_data="autoreg")],
        [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="acc_list")],
        [InlineKeyboardButton(text="🔍 Проверить все", callback_data="acc_check_all")],
        [InlineKeyboardButton(text="👤 Шаблоны профиля", callback_data="acc_setup"),
         InlineKeyboardButton(text="🌐 Прокси-пул", callback_data="proxy_pool")],
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
        [InlineKeyboardButton(text="🔍 Проверить", callback_data=f"acc_check_{acc_id}"),
         InlineKeyboardButton(text="🗑 Удалить", callback_data=f"acc_del_{acc_id}")],
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
        [InlineKeyboardButton(text="🎯 Режим", callback_data=f"camp_mode_{camp_id}")],
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


MODE_LABELS = {
    "comments": "💬 Комментарии",
    "comments_cta": "💬 Комментарии + CTA",
    "stories": "👁 Просмотр Stories",
    "subscribe": "📢 Подписка + просмотр",
}


def camp_mode_kb(camp_id: int, current_mode: str) -> InlineKeyboardMarkup:
    buttons = []
    for mode, label in MODE_LABELS.items():
        check = "✅ " if mode == current_mode else ""
        buttons.append([InlineKeyboardButton(
            text=f"{check}{label}",
            callback_data=f"camp_setmode_{camp_id}_{mode}"
        )])
    buttons.append([InlineKeyboardButton(
        text="◀️ К кампании", callback_data=f"camp_view_{camp_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Шаблоны профиля ---

def acc_setup_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать шаблон", callback_data="tpl_add")],
        [InlineKeyboardButton(text="📋 Список шаблонов", callback_data="tpl_list")],
        [InlineKeyboardButton(text="◀️ К аккаунтам", callback_data="accounts")],
    ])


def tpl_list_kb(templates: list) -> InlineKeyboardMarkup:
    buttons = []
    for tpl in templates:
        buttons.append([InlineKeyboardButton(
            text=f"👤 {tpl['name']}",
            callback_data=f"tpl_view_{tpl['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К шаблонам", callback_data="acc_setup")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def tpl_item_kb(tpl_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔄 Применить ко всем", callback_data=f"tpl_apply_all_{tpl_id}")],
        [InlineKeyboardButton(
            text="📱 Применить к одному", callback_data=f"tpl_apply_pick_{tpl_id}")],
        [InlineKeyboardButton(
            text="🗑 Удалить", callback_data=f"tpl_del_{tpl_id}")],
        [InlineKeyboardButton(text="◀️ К шаблонам", callback_data="acc_setup")],
    ])


def tpl_confirm_del_kb(tpl_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, удалить", callback_data=f"tpl_del_confirm_{tpl_id}"),
         InlineKeyboardButton(
            text="❌ Отмена", callback_data=f"tpl_view_{tpl_id}")],
    ])


def tpl_select_acc_kb(accounts: list, tpl_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(
            text=f"📱 {acc['phone']}",
            callback_data=f"tpl_apply_{tpl_id}_{acc['id']}"
        )])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data=f"tpl_view_{tpl_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Пресеты ---

def presets_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать пресет", callback_data="prs_add")],
        [InlineKeyboardButton(text="📋 Список пресетов", callback_data="prs_list")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def preset_list_kb(presets: list) -> InlineKeyboardMarkup:
    buttons = []
    for prs in presets:
        buttons.append([InlineKeyboardButton(
            text=f"📦 {prs['name']}",
            callback_data=f"prs_view_{prs['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К пресетам", callback_data="presets")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def preset_item_kb(prs_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔄 Активировать", callback_data=f"prs_activate_{prs_id}")],
        [InlineKeyboardButton(
            text="👤 Шаблон профиля", callback_data=f"prs_tpl_{prs_id}"),
         InlineKeyboardButton(
            text="🎯 Режим", callback_data=f"prs_mode_{prs_id}")],
        [InlineKeyboardButton(
            text="📢 Каналы", callback_data=f"prs_channels_{prs_id}"),
         InlineKeyboardButton(
            text="💬 Сообщения", callback_data=f"prs_messages_{prs_id}")],
        [InlineKeyboardButton(
            text="⚙️ Лимиты", callback_data=f"prs_limits_{prs_id}")],
        [InlineKeyboardButton(
            text="🗑 Удалить", callback_data=f"prs_del_{prs_id}")],
        [InlineKeyboardButton(text="◀️ К пресетам", callback_data="presets")],
    ])


def prs_mode_kb(prs_id: int, current_mode: str) -> InlineKeyboardMarkup:
    buttons = []
    for mode, label in MODE_LABELS.items():
        check = "✅ " if mode == current_mode else ""
        buttons.append([InlineKeyboardButton(
            text=f"{check}{label}",
            callback_data=f"prs_setmode_{prs_id}_{mode}"
        )])
    buttons.append([InlineKeyboardButton(
        text="◀️ К пресету", callback_data=f"prs_view_{prs_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prs_tpl_select_kb(templates: list, prs_id: int,
                       current_tpl_id: int | None) -> InlineKeyboardMarkup:
    buttons = []
    for tpl in templates:
        check = "✅ " if tpl["id"] == current_tpl_id else ""
        buttons.append([InlineKeyboardButton(
            text=f"{check}👤 {tpl['name']}",
            callback_data=f"prs_tpl_set_{prs_id}_{tpl['id']}"
        )])
    # Кнопка «без шаблона»
    check = "✅ " if not current_tpl_id else ""
    buttons.append([InlineKeyboardButton(
        text=f"{check}🚫 Без шаблона",
        callback_data=f"prs_tpl_clear_{prs_id}"
    )])
    buttons.append([InlineKeyboardButton(
        text="◀️ К пресету", callback_data=f"prs_view_{prs_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prs_select_items_kb(items: list, prefix: str, prs_id: int,
                         selected_ids: set) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        d = dict(item)
        check = "✅" if d["id"] in selected_ids else "⬜"
        label = d.get("phone") or d.get("username") or d.get("text", "")[:30]
        buttons.append([InlineKeyboardButton(
            text=f"{check} {label}",
            callback_data=f"{prefix}_toggle_{prs_id}_{d['id']}"
        )])
    buttons.append([InlineKeyboardButton(
        text="💾 Сохранить", callback_data=f"prs_view_{prs_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prs_limits_kb(prs_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⏱ Мин. задержка", callback_data=f"prs_set_delay_min_{prs_id}"),
         InlineKeyboardButton(
            text="⏱ Макс. задержка", callback_data=f"prs_set_delay_max_{prs_id}")],
        [InlineKeyboardButton(
            text="🕐 Лимит/час", callback_data=f"prs_set_hourly_{prs_id}"),
         InlineKeyboardButton(
            text="📅 Лимит/день", callback_data=f"prs_set_daily_{prs_id}")],
        [InlineKeyboardButton(
            text="◀️ К пресету", callback_data=f"prs_view_{prs_id}")],
    ])


def prs_confirm_del_kb(prs_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, удалить", callback_data=f"prs_del_confirm_{prs_id}"),
         InlineKeyboardButton(
            text="❌ Отмена", callback_data=f"prs_view_{prs_id}")],
    ])


# --- Авторегистрация ---

def autoreg_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 SMS API ключ", callback_data="areg_set_key"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="areg_balance")],
        [InlineKeyboardButton(text="🌍 Страна", callback_data="areg_country"),
         InlineKeyboardButton(text="🔢 Количество", callback_data="areg_count")],
        [InlineKeyboardButton(text="▶️ Запустить авторег", callback_data="areg_start")],
        [InlineKeyboardButton(text="◀️ К аккаунтам", callback_data="accounts")],
    ])


def autoreg_country_kb(current_country: int) -> InlineKeyboardMarkup:
    from services.autoreg import COUNTRIES
    buttons = []
    for code, name in COUNTRIES.items():
        check = "✅ " if code == current_country else ""
        buttons.append([InlineKeyboardButton(
            text=f"{check}{name}",
            callback_data=f"areg_setcountry_{code}"
        )])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data="autoreg")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Прокси-пул ---

def proxy_pool_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Импорт прокси", callback_data="prx_import")],
        [InlineKeyboardButton(text="📋 Список прокси", callback_data="prx_list")],
        [InlineKeyboardButton(text="🔍 Проверить все", callback_data="prx_check_all")],
        [InlineKeyboardButton(text="📱 Автоназначение", callback_data="prx_auto_assign"),
         InlineKeyboardButton(text="🔄 Ротация", callback_data="prx_rotate")],
        [InlineKeyboardButton(text="🗑 Удалить мёртвые", callback_data="prx_del_dead")],
        [InlineKeyboardButton(text="◀️ К аккаунтам", callback_data="accounts")],
    ])


def proxy_list_kb(proxies: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in proxies:
        status_map = {"alive": "🟢", "dead": "🔴", "unchecked": "⚪"}
        icon = status_map.get(p["status"], "⚪")
        acc = f" 📱" if p["account_id"] else ""
        from urllib.parse import urlparse
        parsed = urlparse(p["url"])
        short = f"{parsed.hostname}:{parsed.port}"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {short}{acc}",
            callback_data=f"prx_view_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(
        text="◀️ К пулу", callback_data="proxy_pool")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def proxy_item_kb(prx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔍 Проверить", callback_data=f"prx_check_{prx_id}"),
         InlineKeyboardButton(
            text="🗑 Удалить", callback_data=f"prx_del_{prx_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="prx_list")],
    ])


def prx_confirm_del_kb(prx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, удалить", callback_data=f"prx_del_confirm_{prx_id}"),
         InlineKeyboardButton(
            text="❌ Отмена", callback_data=f"prx_view_{prx_id}")],
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
        [InlineKeyboardButton(text="📱 По аккаунтам", callback_data="stats_accounts"),
         InlineKeyboardButton(text="📢 По каналам", callback_data="stats_channels")],
        [InlineKeyboardButton(text="🎯 По режимам", callback_data="stats_modes"),
         InlineKeyboardButton(text="📅 По дням", callback_data="stats_daily")],
        [InlineKeyboardButton(text="❌ Ошибки", callback_data="stats_errors")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def stats_sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К статистике", callback_data="stats")],
    ])
