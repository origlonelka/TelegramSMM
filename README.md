# TelegramSMM

Telegram-бот для автоматизации SMM-кампаний. Управление Telegram-аккаунтами, каналами, шаблонами сообщений и автоматическими кампаниями через интерфейс бота.

## Возможности

- **Комментарии** — автоматические комментарии к постам в каналах от имени подключённых аккаунтов
- **Подписка** — массовая подписка аккаунтов на целевые каналы с имитацией просмотра постов
- **Рассылка в ЛС** — отправка личных сообщений пользователям из комментариев каналов
- **Просмотр Stories** — автоматический просмотр и лайк сторис каналов
- **Пресеты** — сохранение и быстрое применение наборов настроек кампаний
- **Пул прокси** — управление прокси для аккаунтов (SOCKS5, HTTP)
- **Spintax** — поддержка синтаксиса `{вариант1|вариант2|вариант3}` в шаблонах сообщений
- **Параллельная работа** — каждый аккаунт работает независимо со своим кулдауном
- **Распределение нагрузки** — каналы распределяются между аккаунтами (round-robin)
- **Импорт аккаунтов** — по номеру телефона, session-строке, .session файлу, tdata архиву

## Требования

- Python 3.11+
- Linux (Ubuntu/Debian/CentOS)
- Telegram Bot API токен (от [@BotFather](https://t.me/BotFather))
- Telegram API ID и API Hash (от [my.telegram.org](https://my.telegram.org))

## Установка на Linux

### 1. Обновление системы и установка зависимостей

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
```

**CentOS / RHEL:**
```bash
sudo yum update -y
sudo yum install -y python3 python3-pip git
```

### 2. Клонирование репозитория

```bash
git clone https://github.com/origlonelka/TelegramSMM.git
cd TelegramSMM
```

### 3. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Установка Python-зависимостей

```bash
pip install -r requirements.txt
```

### 5. Настройка переменных окружения

```bash
cp .env.example .env
nano .env
```

Заполните файл `.env`:

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `ADMIN_IDS` | ID администраторов через запятую |
| `ADMIN_USERNAMES` | Юзернеймы администраторов через запятую |
| `API_ID` | API ID от my.telegram.org |
| `API_HASH` | API Hash от my.telegram.org |

### 6. Запуск

```bash
python main.py
```

### 7. Запуск в фоне (systemd)

Создайте файл сервиса:

```bash
sudo nano /etc/systemd/system/telegramsmm.service
```

Содержимое:

```ini
[Unit]
Description=TelegramSMM Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/TelegramSMM
ExecStart=/home/YOUR_USER/TelegramSMM/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Замените `YOUR_USER` на имя вашего пользователя, затем:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegramsmm
sudo systemctl start telegramsmm
```

Просмотр логов:

```bash
sudo journalctl -u telegramsmm -f
```

## Стек

- **aiogram 3.13** — Telegram Bot API, FSM
- **Pyrogram 2.0** — MTProto (управление пользовательскими аккаунтами)
- **aiosqlite** — асинхронная работа с SQLite
- **APScheduler** — планировщик задач (интервальные и cron-задачи)
- **TgCrypto** — шифрование для tdata-импорта
