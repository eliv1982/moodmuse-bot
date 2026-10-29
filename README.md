# MoodMuse

**Repository:** `moodmuse-bot` — Telegram AI bot for personal mood cards, greetings, visual wishes, and anti-cringe messages.

> **Note:** This project was previously called **SpringPost** (repo name `spring-mood-bot`). Docker image/container/volume names may still use the `springpost` prefix until a dedicated deploy rename.

**English:** Bilingual bot (Russian / English) with two ways to create (guided options, or a free-form description) that both build one **creative brief**, confirm it, and generate a **personalized card or picture**: an AI image, optionally with an inscription printed on it (the user's exact text, an AI suggestion the user approved, or none), plus an optional message under the image. **Images** use the direct **OpenAI Images API** by default (`IMAGE_PROVIDER=openai`, model `gpt-image-2.5-flare`, quality `medium`, 180 s timeout). **Captions, brief reading and image-prompt refinement** use **OpenAI** by default (`TEXT_PROVIDER=openai`). Voice input uses **OpenAI transcriptions** by default (`STT_PROVIDER=openai`) in the free-text steps of both modes (always confirmed before use). **ffmpeg** is required to convert Telegram `.ogg` voice messages to WAV. The earlier **ProxyAPI.ru** (images, Whisper) and **Yandex Cloud** (text) routes remain available as legacy fallbacks via `IMAGE_PROVIDER=proxi`, `STT_PROVIDER=proxi` / `proxiapi` and `TEXT_PROVIDER=yandex`.

**Русский:** Telegram-бот для персональных открыток и поздравлений без «кринжа»: картинка с короткой фразой на ней и расширенная подпись. По умолчанию всё идёт напрямую через OpenAI (картинки, текст, голос); ProxyAPI и YandexGPT остались как устаревшие маршруты.

## Features

- **Two creation modes on one shared brief** — *choose from options* (concept → mood → style → inscription → optional preferences) and *my idea* (describe it in your own words; the bot asks only what is genuinely missing). See [User flow](#user-flow)
- **Explicit confirmation before any paid image call** — the brief is shown in Russian and every field can be edited, or the creation cancelled, without starting over
- **Exact inscriptions** — the user's text (or an approved AI suggestion) is drawn exactly as written; a picture can be made without any text; nothing is ever invented when no inscription was asked for
- Optional **occasion, recipient, restrictions, message under the picture** (AI-written, your own, or none) and **sender signature**
- **Profile settings** — preferred name, language, address form, text tone and length
- Interface and captions: **Russian / English**
- Up to **5 generations per user per day** (UTC); admins exempt
- Photo caption trimmed to **Telegram HTML limit** (1024 chars) with safe escaping
- **English image prompt refinement** via LLM before image generation
- **Anti-cringe** guidance in Russian caption prompts (natural tone, no awkward calques)
- **Finished card** — the image carries the inscription drawn on it (Pillow, bundled Cyrillic-capable font) and the message goes in the Telegram caption
- After each card: **repeat** (no extra API), **new caption** (rewrites only what the model wrote, on the same image, no image generation), **new image** (same inscription and message on a fresh image), create another, change language. A card whose inscription and message the user fixed offers only repeat and new image
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

**`/start`** opens the home menu (new users are first asked which name to use). Tap **Create a card** and pick one of two equally accessible modes. The creation screens, buttons and messages are in Russian; the card's own texts follow the language set with `/lang` or in profile settings.

### Mode 1 — choose from options

1. **Concept or purpose** — a quick pick (birthday, New Year, 8 March, thanks, just because, business) or your own idea (text or voice).
2. **Mood** — eight presets, *AI decides*, or your own words.
3. **Visual style** — the eight styles, *AI decides*, or your own words.
4. **Inscription** — your exact text, *AI suggestions* (shown first; they reach the image only after you approve one), or no text.
5. **Optional preferences** — occasion, recipient, restrictions, message under the picture (AI / your own / none), sender signature. Skipped with one tap.
6. **Confirmation.**

### Mode 2 — my idea

Describe everything in one message (text or voice). The text model reads it into the same brief; deterministic checks then decide what the user really said (see rules below). The bot asks a follow-up only when there is no usable concept (asked until there is one, with *Back* and *Cancel* always available). Optional fields, including a greeting's inscription, stay editable on confirmation.

Everything else (mood, style, occasion, recipient, restrictions, message, signature) is taken if mentioned and otherwise left to be edited on the confirmation screen; it is never collected for completeness. A sufficient description goes straight to confirmation. If the text model is unavailable the message itself becomes the concept and explicit signals are still read from its wording.

### Confirmation

The structured brief is shown in Russian: idea, mood, style, the inscription (exact text and where it came from, an explicit *no text*, or *not specified — no text will appear*), occasion, recipient, restrictions, message under the picture, signature. Buttons: **Create**, one **edit** button per field (returns to this screen), **Cancel**. **No image-provider call happens before “Create”.** The only AI calls made while composing are text-model calls (reading a description, proposing an inscription) and, if voice is used, speech recognition.

Back, edit and cancel keep every unrelated answer. A provider or delivery error returns to this screen with the brief intact (retry or edit); the daily limit counts successful generations only. Pressing *Create* twice generates once.

### Brief rules

- A **concept is required**; every other value may be set, delegated to the AI (mood, style) or omitted.
- The inscription has four distinct states: *unspecified* (never filled in on the user's behalf — nothing is drawn), *explicit no text*, *exact text* (user-written or approved AI suggestion; drawn unchanged), and *AI suggestion requested* (never drawn until approved).
- From a free-form message an inscription is accepted only if it appears **verbatim** in what the user wrote, and *no text* only if the user said so; otherwise the model's reading is ignored.
- Original descriptions are retained verbatim independently of extraction and its field limits. Their hard constraints are authoritative and appended after image-prompt refinement, together with a rule that the image model must print no text (the renderer draws the inscription afterwards). Explicitly replacing or clearing restrictions supersedes earlier restrictions. This preserves instructions; image-model compliance is not guaranteed.
- A user-written inscription must be drawable as written: up to 120 characters, characters the bundled font has (no emoji), and fitting the image without the “…” shortening used for AI phrases. Otherwise the user is told why and asked to change it; the text is never altered.
- The message under the picture defaults to *none* for both greetings and plain pictures; AI writes it only when selected or explicitly requested. The confirmation shows the choice.

## Finished card

A card is **image + optional inscription drawn on the image + optional message as the caption**. Cards made before guided creation always have both, written by the model; each text of a newer card is recorded as model-written (`ai`), exact (`text` / `user`) or deliberately absent (`none`), and the regeneration buttons only ever replace what the model wrote.

- Legacy (model-written) cards: one text request returns JSON with a `short` phrase (printed on the image) and the `full` caption. If the model does not return that JSON, the whole reply becomes the caption and the card goes out without a phrase. Guided creation never asks the model for the inscription; it requests only the caption when the message is AI-written.
- The phrase is drawn by [`services/card_render.py`](services/card_render.py) with Pillow on a worker thread: wrapped, centred near the bottom, margins kept, shrunk to fit (an overflowing AI phrase ends with “…”; exact inscriptions are validated beforehand and never shortened, and explicit line breaks are kept), over a dark gradient so it stays readable on bright images. It uses the bundled **PT Serif Bold** (SIL OFL 1.1, Cyrillic + Latin; see `assets/fonts/`).
- The **clean provider image is stored** (SQLite, `last_card.original_image`, latest card per user only) alongside the card context in the same row. Text-only actions redraw on that clean image, so nothing is drawn on top of earlier text and no image is generated again.
- If drawing fails for any reason, the clean image and the caption are sent; for an exact inscription the user is also told the text could not be applied (it stays stored for “new image”).
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
│   ├── creation.py           # guided creation: both modes, confirmation, edit/back/cancel, generation
│   ├── main.py               # regeneration, idle chat, /start, /help (also still holds the previous fixed wizard, now unreachable)
│   ├── profile.py            # onboarding and profile settings
│   └── admin.py              # admin commands
├── services/
│   ├── card_generation.py    # prompt refine + image + caption pipeline (run_brief_generation for briefs)
│   ├── brief_ai.py           # reads a free-form request into a brief; proposes inscriptions (text model only)
│   ├── card_render.py        # draws the inscription on the card image (Pillow); checks exact inscriptions
│   ├── providers/            # text / image / speech-to-text providers and factories
│   ├── storage.py            # SQLite: profiles, daily limits, last card
│   ├── small_talk.py         # idle-chat and returning-user greetings
│   └── ...                   # ProxyAPI / Yandex clients, speech-to-text, audio prep
├── assets/fonts/             # bundled PT Serif Bold + OFL license
├── utils/                    # RU/EN copy (i18n), prompts, creative brief + creation UI, profile UI helpers, logging
└── tests/                    # offline pytest suite (mocked providers, fake config)
```

## License

No license file is included in this repository, so no license is granted at this time.
