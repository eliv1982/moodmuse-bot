# SpringPost

**English:** Telegram bot for personalized greeting cards. **Images** are generated via [ProxyAPI.ru](https://proxyapi.ru) (OpenAI-compatible API, default `gpt-image-1`). **Captions and image-prompt refinement** use **Yandex Cloud Foundation Models** (YandexGPT). Bilingual UI (Russian / English), per-user daily limits, SQLite storage, JSON logging, Docker-ready.

**Русский:** Telegram-бот для персонализированных поздравительных открыток на двух AI-бэкендах: картинка — ProxyAPI, текст и доработка промпта — YandexGPT.

## Features

- Interface and card captions: **Russian / English**
- Up to **5 generations per user per day** (UTC); admins exempt
- Photo caption trimmed to **Telegram HTML limit** (1024 chars) with safe escaping
- **English image prompt refinement** via LLM before ProxyAPI
- After each card: **repeat** (no extra API), **new caption**, **new image**, create another, change language
- Admin commands: `/stats`, `/smalltalk_on`, `/smalltalk_off`, `/maintenance …`
- **JSON logs** with `user_id` and `event` (handy with `docker logs`)

## Requirements

- Python 3.11+
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- **ProxyAPI.ru** key (images + Whisper for voice)
- **Yandex Cloud**: folder ID + service account API key with Foundation Models access ([docs](https://yandex.cloud/en/docs/foundation-models/))

## Local setup

```bash
cd SpringPost
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
copy .env.example .env            # Windows: copy; Linux: cp
# Set BOT_TOKEN, PROXI_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID; optional ADMIN_USER_IDS

python bot.py
```

Tests:

```bash
pytest -q
```

## Docker

From the project directory (same folder as `docker-compose.yml` and `.env`):

```bash
docker compose up -d --build
```

SQLite and rate-limit data live in volume **`springpost_data`** → `/app/data` in the container.

**Important:** `YANDEX_API_KEY` and `YANDEX_FOLDER_ID` must be in **`.env` next to `docker-compose.yml`**, and the file must be listed as `env_file: .env` for the bot service. After editing `.env`, recreate the container:

```bash
docker compose up -d --force-recreate
```

Verify merged config (should list both variables under `bot.environment`):

```bash
docker compose config | grep YANDEX_
```

VPS-oriented steps: see **[DEPLOY.md](DEPLOY.md)**.

## Environment variables (summary)

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token |
| `PROXI_API_KEY` | ProxyAPI.ru key |
| `PROXI_BASE_URL` | Default `https://openai.api.proxyapi.ru` |
| `YANDEX_API_KEY` | Yandex Cloud API key |
| `YANDEX_FOLDER_ID` | Yandex Cloud folder ID |
| `ADMIN_USER_IDS` | Comma-separated numeric Telegram user IDs |
| `DAILY_GENERATION_LIMIT` | Per-user daily cap (default 5) |
| `DATA_DIR` | SQLite directory |
| `LOG_JSON` | `true` / `false` log format |

Full list: **`.env.example`**.

## User flow (5 steps)

1. **`/start`** — language on first visit, then **who the card is for** (inline buttons).
2. **Image idea** — text or voice, or “surprise me” / «придумай сам».
3. **Holiday or occasion** — text or voice (e.g. birthday, “just because”).
4. **Image style** — inline buttons.
5. **Caption style** — inline buttons → generation (prompt refine + image + caption).

## Project layout

```
SpringPost/
├── bot.py
├── config.py
├── requirements.txt
├── pytest.ini
├── Dockerfile
├── docker-compose.yml
├── DEPLOY.md
├── handlers/
│   ├── main.py
│   ├── admin.py
│   ├── middlewares.py
│   ├── filters.py
│   └── states.py
├── services/
│   ├── proxi.py
│   ├── yandex_gpt.py
│   ├── card_generation.py
│   ├── speech_to_text.py
│   └── storage.py
├── utils/
│   ├── prompts.py
│   ├── translate.py
│   ├── i18n.py
│   ├── logging_config.py
│   └── bot_commands.py
└── tests/
```

## License

MIT.
