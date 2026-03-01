# SpringPost

Telegram-бот для создания персонализированных поздравительных открыток с помощью двух AI:

- **Изображение** — ProxiAPI (модель `gpt-image-1-mini`)
- **Текст** — GigaChat (API Сбера)

## Требования

- Python 3.11+
- Аккаунт Telegram (токен бота через [@BotFather](https://t.me/BotFather))
- Ключ ProxiAPI
- Учётные данные GigaChat (client_id и client_secret в [кабинете разработчика Сбера](https://developers.sber.ru/))

## Установка и запуск локально

```bash
# Клонирование / переход в каталог проекта
cd SpringPost

# Виртуальное окружение (рекомендуется)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# Зависимости
pip install -r requirements.txt

# Настройка
copy .env.example .env
# Отредактируйте .env: BOT_TOKEN, PROXI_API_KEY, GIGACHAT_CREDENTIALS и т.д.

# Запуск
python bot.py
```

## Сборка и запуск через Docker

### Сборка образа

```bash
docker build -t springpost:latest .
```

### Запуск контейнера

Создайте файл `.env` в корне проекта (по образцу `.env.example`), затем:

```bash
docker run --env-file .env --name springpost -d springpost:latest
```

Или через Docker Compose:

```bash
docker compose up -d
```

Остановка:

```bash
docker compose down
# или
docker stop springpost
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram-бота |
| `PROXI_API_KEY` | Ключ API ProxiAPI (Proxed.AI) |
| `PROXI_BASE_URL` | Базовый URL ProxiAPI (по умолчанию `https://api.proxed.ai`) |
| `GIGACHAT_CREDENTIALS` | Строка `client_id:client_secret` из личного кабинета GigaChat |
| `GIGACHAT_SCOPE` | Область доступа (по умолчанию `GIGACHAT_API_PERS`) |

## Сценарий работы бота

1. Пользователь отправляет `/start`.
2. Выбор повода: для клиентов/партнёров, для коллег, для близких.
3. Описание картинки (или «придумай сам»).
4. Праздник/повод (например, 8 Марта, 1 Мая).
5. Стиль изображения (реалистичный, мультяшный, акварель и др.).
6. Стиль текста (деловой, душевный, стихи, с юмором).
7. Параллельная генерация изображения и текста, отправка открытки и кнопка «Создать ещё одну».

## Структура проекта

```
SpringPost/
├── bot.py              # Точка входа
├── config.py           # Настройки из .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── handlers/           # Обработчики команд и FSM
│   ├── __init__.py
│   ├── main.py
│   └── states.py
├── services/           # API-клиенты
│   ├── proxi.py        # ProxiAPI (изображения)
│   └── gigachat.py     # GigaChat (текст)
└── utils/
    ├── prompts.py     # Формирование промптов
    └── translate.py    # Поддержка перевода описания для изображения
```

## Деплой на VPS

1. Установите Docker и Docker Compose на сервер.
2. Скопируйте проект и создайте `.env` с реальными ключами.
3. Выполните:
   ```bash
   docker compose up -d
   ```
4. Бот работает в режиме **polling**, webhook не требуется.

## Лицензия

MIT.
