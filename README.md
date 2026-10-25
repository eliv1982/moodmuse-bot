# MoodMuse

**Repository:** `moodmuse-bot` — Telegram AI bot for personal mood cards, greetings, visual wishes, and anti-cringe messages.

> **Note:** This project was previously called **SpringPost** (repo name `spring-mood-bot`). Docker image/container/volume names may still use the `springpost` prefix until a dedicated deploy rename.

**English:** Bilingual bot (Russian / English) that walks users through a short wizard and generates a **personalized card**: an AI image plus a caption tuned for tone and audience. **Images** use [ProxyAPI.ru](https://proxyapi.ru) (OpenAI-compatible API, default `gpt-image-1`). **Captions and image-prompt refinement** use **Yandex Cloud Foundation Models** (YandexGPT) by default, with an optional **OpenAI** text provider (`TEXT_PROVIDER=openai`). Voice input uses **OpenAI transcriptions** by default (`STT_PROVIDER=openai`) after the user picks **Custom wishes** (text or voice in the same step). **ffmpeg** is required to convert Telegram `.ogg` voice messages to WAV. **ProxyAPI Whisper** remains available as a legacy fallback via `STT_PROVIDER=proxi` (or `STT_PROVIDER=proxiapi`).

**Русский:** Telegram-бот для персональных открыток и поздравлений без «кринжа»: картинка через ProxyAPI, текст и доработка промпта — YandexGPT (или OpenAI при настройке).

## Features

- **Mood cards & greetings** — occasion, holiday (with optional age/date/period details for birthdays and anniversaries), image idea, image style, caption style
- Optional **recipient greeting/address** and **sender signature** on the card
- **Profile settings** — preferred name, language, address form, text tone and length
- Interface and captions: **Russian / English**
- Up to **5 generations per user per day** (UTC); admins exempt
- Photo caption trimmed to **Telegram HTML limit** (1024 chars) with safe escaping
- **English image prompt refinement** via LLM before image generation
- **Anti-cringe** guidance in Russian caption prompts (natural tone, no awkward calques)
- After each card: **repeat** (no extra API), **new caption**, **new image**, create another, change language
- [Admin commands](#admin-commands): `/stats`, `/smalltalk_on`, `/smalltalk_off`, `/maintenance …`, `/dev_reset_me`
- **JSON logs** with `user_id`, `event` and any other structured fields attached to the log call (handy with `docker logs`)

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
# Set BOT_TOKEN, ALLOWED_USER_IDS, PROXI_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID; optional ADMIN_USER_IDS, TEXT_PROVIDER

python bot.py
```

Tests run offline with mocked providers and fake config — no `.env`, API keys or network needed:

```bash
pytest -q
```

GitHub Actions runs the same command on pushes to `main` and on pull requests ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)); it needs no secrets.

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
| `ALLOWED_USER_IDS` | **Required.** Comma-separated numeric Telegram user IDs allowed to use the bot; empty or invalid means nobody ([details](#private-access)) |
| `ADMIN_USER_IDS` | Comma-separated numeric Telegram user IDs (admin commands, limit exemption; does not grant access) |
| `DAILY_GENERATION_LIMIT` | Per-user daily cap (default 5) |
| `DATA_DIR` | SQLite directory |
| `LOG_JSON` | `true` / `false` log format |

Full list: **`.env.example`**.

## Private access

MoodMuse is a private bot: only Telegram users listed in `ALLOWED_USER_IDS` can use it. Anyone else gets a short "invite-only" notice (Russian, or English if their language was saved earlier) and nothing more: no AI or voice-transcription calls, nothing stored for them. The check runs before every command (admin commands included), wizard step, text, voice message and button press. Pressing a button always gets a response, so Telegram's loading spinner never hangs. Repeated messages from the same person get the notice at most once every 10 minutes.

```env
ALLOWED_USER_IDS=<owner_telegram_id>,<second_user_telegram_id>   # replace with real numeric ids
```

- **Fails closed.** Missing, empty or malformed means nobody is allowed, and a single malformed entry rejects the whole list (the startup log says so without printing the values). Entries must be plain positive integers.
- **Admins are not implicitly allowed.** An admin must be listed in both `ALLOWED_USER_IDS` and `ADMIN_USER_IDS`; otherwise admin commands are denied like everything else.
- **Restart to apply changes.** The list is read once at startup. In Docker, `docker compose restart` does not re-read `.env`; use `docker compose up -d --force-recreate`. A restart also drops in-progress wizard sessions (they are held in memory) and any generation that is running, so people mid-card need to send `/start` again. Adding or removing someone only takes effect after that restart.
- **Finding your Telegram user ID.** Start the bot with `ALLOWED_USER_IDS` empty, send it any message from your account, and read the `access_denied user_id=...` line in its log (`docker compose logs bot | grep access_denied`). Put that number in `.env` and restart. You do not need to share the bot token with anyone; third-party "what is my ID" bots also work, but the log approach involves no third party.
- The daily generation limit is a separate cost control, not an access control; it is unchanged.

## User flow

**`/start`** opens the home menu (new users are first asked which name to use). Tap **Create a card** to start the wizard (interface/caption language is set with `/lang` or in profile settings):

1. **Recipient** — who the card is for (inline buttons).
2. **Holiday or occasion** — text or voice (e.g. birthday, “just because”). For birthday/anniversary-type occasions the bot then offers **optional occasion details** (age, date or period) — Yes/No, then text or voice.
3. **Image idea** — «придумай сам» / “surprise me”, or custom wishes (text or voice).
4. **Image style** — inline buttons.
5. **Caption style** — inline buttons.
6. **Recipient greeting/address** (optional) — Yes/No, then text or voice (e.g. “Dear colleagues”).
7. **Sender signature** (optional) — Yes/No, then text or voice (e.g. “With love, Lena”).

Free-text answers (typed or voice) are echoed back with an “Is that correct?” confirmation. There is no separate confirmation screen after the last step: the bot posts a **summary of your choices**, which doubles as the progress status, and generation (prompt refine + image + caption) starts immediately. On success the summary is replaced by the finished card; on a provider error the user sees a short generic message (details go to the server log only) and returns to the signature step — answering it again retries generation.

## Admin commands

Available only to Telegram user IDs listed in `ADMIN_USER_IDS` **that are also in `ALLOWED_USER_IDS`** (see [Private access](#private-access)). Admins are also exempt from the daily generation limit and from maintenance mode. These commands are not shown in the Telegram command menu (which lists `/start`, `/cancel`, `/lang`, `/help`).

| Command | Effect |
|---------|--------|
| `/stats` | Generations today and in total, unique users today, daily limit, small-talk and maintenance status |
| `/smalltalk_on`, `/smalltalk_off` | Enable / disable AI replies to idle chat (off → template replies only) |
| `/maintenance <text>` | Show `<text>` to non-admins instead of processing their updates; `/maintenance off` (or no text) clears it |
| `/dev_reset_me` | Testing helper: deletes **your own** saved profile (language, name, address/tone/length preferences) and clears the wizard state so first-run onboarding can be repeated. Daily counts, generation history and your last card are kept. Non-admins get a denial message. Also available as a 🧪 button on the profile screen for admins. |

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
├── .github/workflows/ci.yml  # offline test run
├── handlers/                 # aiogram routers, FSM states, middleware
│   ├── main.py               # card wizard, generation/regeneration, idle chat, /start, /help
│   ├── profile.py            # onboarding and profile settings
│   └── admin.py              # admin commands
├── services/
│   ├── card_generation.py    # prompt refine + image + caption pipeline
│   ├── providers/            # text / image / speech-to-text providers and factories
│   ├── storage.py            # SQLite: profiles, daily limits, last card
│   ├── small_talk.py         # idle-chat and returning-user greetings
│   └── ...                   # ProxyAPI / Yandex clients, speech-to-text, audio prep
├── utils/                    # RU/EN copy (i18n), prompts, wizard and profile UI helpers, logging
└── tests/                    # offline pytest suite (mocked providers, fake config)
```

## License

No license file is included in this repository, so no license is granted at this time.
