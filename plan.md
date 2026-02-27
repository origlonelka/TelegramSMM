# TelegramSMM — План реализации

## Стек
- **Python 3.11+**
- **aiogram 3** — Telegram Bot API (управление ботом)
- **Pyrogram** — Telegram MTProto (userbot-аккаунты для отправки комментариев)
- **SQLite + aiosqlite** — хранение данных
- **APScheduler** — планировщик задач для автоматической отправки

## Структура проекта
```
TelegramSMM/
├── bot/
│   ├── __init__.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py          # /start, главное меню
│   │   ├── accounts.py       # управление аккаунтами
│   │   ├── channels.py       # управление каналами
│   │   ├── messages.py       # шаблоны сообщений
│   │   ├── campaigns.py      # управление рассылками
│   │   └── settings.py       # лимиты и настройки
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── inline.py         # inline-клавиатуры
│   └── middlewares/
│       └── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py             # конфигурация (токены, лимиты)
│   └── scheduler.py          # планировщик отправки комментариев
├── db/
│   ├── __init__.py
│   ├── database.py           # подключение к SQLite
│   └── models.py             # таблицы: accounts, channels, messages, campaigns, logs
├── services/
│   ├── __init__.py
│   ├── account_manager.py    # авторизация и управление Pyrogram-сессиями
│   ├── channel_parser.py     # парсинг каналов по ключевым словам
│   └── commenter.py          # отправка комментариев с лимитами
├── sessions/                  # папка для .session файлов Pyrogram
├── requirements.txt
├── .env.example
├── .gitignore
└── main.py                    # точка входа
```

## Функционал

### 1. Управление аккаунтами
- Добавление Telegram-аккаунтов (phone + api_id + api_hash)
- Авторизация через Pyrogram (код подтверждения через бота)
- Статус аккаунта (активен/заблокирован/лимит)

### 2. Управление каналами
- Поиск каналов по ключевым словам (например "Hytale")
- Ручное добавление каналов по @username или ссылке
- Проверка: открыты ли комментарии в канале

### 3. Шаблоны сообщений
- Создание нескольких шаблонов рекламных комментариев
- Ротация шаблонов (чтобы не отправлять одно и то же)
- Поддержка переменных ({random_emoji}, {account_name} и т.д.)

### 4. Рассылка комментариев
- Автоматическая отправка комментариев в новые посты каналов
- Распределение нагрузки между аккаунтами

### 5. Лимиты (защита от бана)
- Лимит комментариев на аккаунт в час / в день
- Случайная задержка между комментариями (мин/макс)
- Пауза аккаунта при приближении к лимиту
- Задержка между действиями (flood wait handling)

### 6. Логирование
- Лог каждого отправленного комментария
- Статистика по аккаунтам и каналам

## Таблицы БД

### accounts
- id, phone, api_id, api_hash, session_file, status, comments_today, comments_hour, last_comment_at

### channels
- id, username, title, has_comments, added_at

### messages
- id, text, is_active

### campaigns
- id, name, is_active, delay_min, delay_max, hourly_limit, daily_limit

### campaign_channels
- campaign_id, channel_id

### campaign_accounts
- campaign_id, account_id

### logs
- id, account_id, channel_id, message_id, post_id, sent_at, status

## Шаги реализации
1. Создать структуру проекта, requirements.txt, .gitignore
2. Настроить БД (models.py, database.py)
3. Сделать бота: главное меню + управление аккаунтами
4. Добавить управление каналами и парсинг
5. Добавить шаблоны сообщений
6. Реализовать commenter.py с лимитами
7. Добавить планировщик (scheduler)
8. Добавить логирование и статистику
