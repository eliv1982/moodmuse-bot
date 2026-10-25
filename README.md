# MoodMuse

**Repository:** `moodmuse-bot` — Telegram AI bot for personal mood cards, greetings, visual wishes, and anti-cringe messages.

> **Note:** This project was previously called **SpringPost** (repo name `spring-mood-bot`). Docker image/container/volume names may still use the `springpost` prefix until a dedicated deploy rename.

**English:** Bilingual bot (Russian / English) that walks users through a short wizard and generates a **personalized card**: an AI image with a short phrase printed on it, plus an expanded caption tuned for tone and audience. **Images** use the direct **OpenAI Images API** by default (`IMAGE_PROVIDER=openai`, model `gpt-image-2.5-flare`, quality `medium`, 180 s timeout). **Captions and image-prompt refinement** use **OpenAI** by default (`TEXT_PROVIDER=openai`); one text request returns both the short phrase and the expanded caption. Voice input uses **OpenAI transcriptions** by default (`STT_PROVIDER=openai`) after the user picks **Custom wishes** (text or voice in the same step). **ffmpeg** is required to convert Telegram `.ogg` voice messages to WAV. The earlier **ProxyAPI.ru** (images, Whisper) and **Yandex Cloud** (text) routes remain available as legacy fallbacks via `IMAGE_PROVIDER=proxi`, `STT_PROVIDER=proxi` / `proxiapi` and `TEXT_PROVIDER=yandex`.

**Русский:** Telegram-бот для персональных открыток и поздравлений без «кринжа»: картинка с короткой фразой на ней и расширенная подпись. По умолчанию всё идёт напрямую через OpenAI (картинки, текст, голос); ProxyAPI и YandexGPT остались как устаревшие маршруты.

## Features

- **Mood cards & greetings** — occasion, holiday (with optional age/date/period details for birthdays and anniversaries), image idea, image style, caption style
- Optional **recipient greeting/address** and **sender signature** on the card
- **Profile settings** — preferred name, language, address form, text tone and length
- Interface and captions: **Russian / English**
- Up to **5 generations per user per day** (UTC); admins exempt
- Photo caption trimmed to **Telegram HTML limit** (1024 chars) with safe escaping
- **English image prompt refinement** via LLM before image generation
- **Anti-cringe** guidance in Russian caption prompts (natural tone, no awkward calques)
- **Finished card** — the image carries a short phrase drawn on it (Pillow, bundled Cyrillic-capable font) and the expanded text goes in the Telegram caption; both come from one text request
- After each card: **repeat** (no extra API), **new caption** (new phrase + caption on the same image, no image generation), **new image** (same phrase and caption on a fresh image), create another, change language
- [Admin commands](#admin-commands): `/stats`, `/smalltalk_on`, `/smalltalk_off`, `/maintenance …`, `/dev_reset_me`
- **JSON logs** with `user_id`, `event` and any other structured fields attached to the log call (handy with `docker logs`)

## Requirements

- Python 3.11+
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- **OpenAI** API key (`OPENAI_API_KEY`): images, text and voice input all use it by default
- Optional legacy routes: **ProxyAPI.ru** key for `IMAGE_PROVIDER=proxi` / `STT_PROVIDER=proxi`; **Yandex Cloud** folder ID + API key with Foundation Models access for `TEXT_PROVIDER=yandex` ([docs](https://yandex.cloud/en/docs/foundation-models/))
- Pillow (installed from `requirements.txt`) draws the short phrase on the card image with the bundled PT Serif Bold font (SIL OFL 1.1, see `assets/fonts/`)

## Local setup

```bash
git clone <url> moodmuse-bot
cd moodmuse-bot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
copy .env.example .env          # Windows: copy; Linux: cp
# Set BOT_TOKEN, ALLOWED_USER_IDS, OPENAI_API_KEY; optional ADMIN_USER_IDS

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

**Important:** `OPENAI_API_KEY` (and `YANDEX_API_KEY` / `YANDEX_FOLDER_ID` or `PROXI_API_KEY` if you select a legacy provider) must be in **`.env` next to `docker-compose.yml`**, and the file must be listed as `env_file: .env` for the bot service. After editing `.env`, recreate the container:

```bash
docker compose up -d --force-recreate
```

Verify merged config (should list the variables under `bot.environment`):

```bash
docker compose config | grep OPENAI_
```

VPS-oriented steps: see **[DEPLOY.md](DEPLOY.md)**.

## Environment variables (summary)

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token |
| `TEXT_PROVIDER` | `openai` (default) or legacy `yandex` for captions / prompt refine |
| `IMAGE_PROVIDER` | `openai` (default, direct Images API) or legacy `proxi` (ProxyAPI.ru) |
| `OPENAI_API_KEY` | OpenAI API key (text, images and voice by default) |
| `OPENAI_BASE_URL` | Default `https://api.openai.com/v1` |
| `OPENAI_TEXT_MODEL` | Default `gpt-4o-mini` |
| `OPENAI_IMAGE_MODEL` | Default `gpt-image-2.5-flare` |
| `OPENAI_IMAGE_QUALITY` | `low` / `medium` / `high` / `auto`; default `medium`. Empty omits it; sent only to `gpt-image*` models and never on the ProxyAPI route |
| `OPENAI_IMAGE_SIZE` | Default `1024x1024` |
| `OPENAI_IMAGE_TIMEOUT` | Seconds; default `180` |
| `PROXI_API_KEY` | ProxyAPI.ru key (legacy image / Whisper route) |
| `PROXI_BASE_URL` | Default `https://openai.api.proxyapi.ru` |
| `PROXI_IMAGE_MODEL` | Default `gpt-image-2.5-flare` (legacy route; not verified against ProxyAPI.ru) |
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

## Finished card

A card is **image + short phrase drawn on the image + expanded caption**.

- One text request returns JSON with a `short` phrase (printed on the image) and the `full` caption (the Telegram caption, written as before). If the model does not return that JSON, the whole reply becomes the caption and the card goes out without a phrase.
- The phrase is drawn by [`services/card_render.py`](services/card_render.py) with Pillow on a worker thread: wrapped, centred near the bottom, margins kept, shrunk to fit (an overflowing phrase ends with “…”), over a dark gradient so it stays readable on bright images. It uses the bundled **PT Serif Bold** (SIL OFL 1.1, Cyrillic + Latin; see `assets/fonts/`).
- The **clean provider image is stored** (SQLite, `last_card.original_image`, latest card per user only) alongside the card context in the same row. Text-only actions redraw on that clean image, so nothing is drawn on top of earlier text and no image is generated again.
- If drawing fails for any reason, the clean image and the expanded caption are sent.
- Cards saved before this feature have no clean original: **new caption** and **language switch** change only the caption, as before; **new image** works and starts keeping an original, after which the next text change embeds a phrase.
- A user's card operations (new card, new caption, new image, language switch) run one at a time; a second one gets a short “still being prepared” notice instead of racing the first. **Repeat** only re-sends the delivered card and is never blocked.

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
│   ├── card_generation.py    # prompt refine + image + short phrase / caption pipeline
│   ├── card_render.py        # draws the short phrase on the card image (Pillow)
│   ├── providers/            # text / image / speech-to-text providers and factories
│   ├── storage.py            # SQLite: profiles, daily limits, last card
│   ├── small_talk.py         # idle-chat and returning-user greetings
│   └── ...                   # ProxyAPI / Yandex clients, speech-to-text, audio prep
├── assets/fonts/             # bundled PT Serif Bold + OFL license
├── utils/                    # RU/EN copy (i18n), prompts, wizard and profile UI helpers, logging
└── tests/                    # offline pytest suite (mocked providers, fake config)
```

## License

No license file is included in this repository, so no license is granted at this time.
