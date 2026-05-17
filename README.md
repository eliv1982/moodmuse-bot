# MoodMuse

**Repository:** `moodmuse-bot` — Telegram AI bot for personal mood cards, greetings, visual wishes, and anti-cringe messages.

> **Note:** This project was previously called **SpringPost** (repo name `spring-mood-bot`). Docker image/container/volume names may still use the `springpost` prefix until a dedicated deploy rename.

**English:** Bilingual bot (Russian / English) that walks users through a short wizard and generates a **personalized card**: an AI image plus a caption tuned for tone and audience. **Images** use [ProxyAPI.ru](https://proxyapi.ru) (OpenAI-compatible API, default `gpt-image-1`). **Captions and image-prompt refinement** use **Yandex Cloud Foundation Models** (YandexGPT) by default, with an optional **OpenAI** text provider (`TEXT_PROVIDER=openai`). Voice input uses **OpenAI transcriptions** by default (`STT_PROVIDER=openai`) after the user picks **Custom wishes** (text or voice in the same step). **ffmpeg** is required to convert Telegram `.ogg` voice messages to WAV. **ProxyAPI Whisper** remains available as a legacy fallback via `STT_PROVIDER=proxi` (or `STT_PROVIDER=proxiapi`).

**Русский:** Telegram-бот для персональных открыток и поздравлений без «кринжа»: картинка через ProxyAPI, текст и доработка промпта — YandexGPT (или OpenAI при настройке).

## Features

- **Mood cards & greetings** — occasion, image idea, holiday, image style, caption style
- Interface and captions: **Russian / English**
- Up to **5 generations per user per day** (UTC); admins exempt
- Photo caption trimmed to **Telegram HTML limit** (1024 chars) with safe escaping
- **English image prompt refinement** via LLM before image generation
- **Anti-cringe** guidance in Russian caption prompts (natural tone, no awkward calques)
- After each card: **repeat** (no extra API), **new caption**, **new image**, create another, change language
- Admin commands: `/stats`, `/smalltalk_on`, `/smalltalk_off`, `/maintenance …`
- **JSON logs** with `user_id` and `event` (handy with `docker logs`)

## Requirements

- Python 3.11+
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- **OpenAI** API key for voice input by default (`STT_PROVIDER=openai`); **ProxyAPI.ru** for images (and legacy voice STT via `STT_PROVIDER=proxi`)
- **Yandex Cloud** (default text): folder ID + API key with Foundation Models access ([docs](https://yandex.cloud/en/docs/foundation-models/))
- **OpenAI** (optional text): `OPENAI_API_KEY` when `TEXT_PROVIDER=openai`

## Local setup

```bash
git clone <url> moodmuse-bot
cd moodmuse-bot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
copy .env.example .env          # Windows: copy; Linux: cp
# Set BOT_TOKEN, PROXI_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID; optional ADMIN_USER_IDS, TEXT_PROVIDER

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

SQLite and rate-limit data live in Docker volume **`springpost_data`** (legacy name) → `/app/data` in the container. The running container is named **`springpost`**; image tag **`springpost:latest`**. See [DEPLOY.md](DEPLOY.md) before renaming these in production.

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
| `TEXT_PROVIDER` | `yandex` (default) or `openai` for captions / prompt refine |
| `OPENAI_API_KEY` | OpenAI API key when `TEXT_PROVIDER=openai` |
| `OPENAI_BASE_URL` | Default `https://api.openai.com/v1` |
| `OPENAI_TEXT_MODEL` | Default `gpt-4o-mini` |
| `PROXI_API_KEY` | ProxyAPI.ru key |
| `PROXI_BASE_URL` | Default `https://openai.api.proxyapi.ru` |
| `STT_PROVIDER` | `openai` (default); legacy `proxi` / `proxiapi` for ProxyAPI Whisper |
| `OPENAI_STT_MODEL` | Default `gpt-4o-mini-transcribe` |
| `FFMPEG_BINARY` | Path to `ffmpeg` for Telegram voice `.ogg` → WAV (default `ffmpeg`) |
| `YANDEX_API_KEY` | Yandex Cloud API key |
| `YANDEX_FOLDER_ID` | Yandex Cloud folder ID |
| `ADMIN_USER_IDS` | Comma-separated numeric Telegram user IDs |
| `DAILY_GENERATION_LIMIT` | Per-user daily cap (default 5) |
| `DATA_DIR` | SQLite directory |
| `LOG_JSON` | `true` / `false` log format |

Full list: **`.env.example`**.

## User flow

After **`/start`** (language on first visit):

1. **Recipient** — who the card is for (inline buttons).
2. **Holiday or occasion** — text or voice (e.g. birthday, “just because”).
3. **Image idea** — «придумай сам» / “surprise me”, or custom wishes (text or voice).
4. **Image style** — inline buttons.
5. **Caption style** — inline buttons.
6. **Summary → generation** — review your choices, then card creation (prompt refine + image + caption).

## Project layout

```
moodmuse-bot/
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
│   ├── storage.py
│   └── providers/
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
