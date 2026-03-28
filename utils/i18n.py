"""
UI strings: Russian / English.
"""
from __future__ import annotations

from typing import Literal

Lang = Literal["ru", "en"]

MESSAGES: dict[str, dict[Lang, str]] = {
    "start_intro": {
        "ru": (
            "🌸 Привет! Я бот хорошего настроения. Создам открытку с картинкой и подписью "
            "к любому празднику или поводу.\n\nВыберите язык / Choose language:"
        ),
        "en": (
            "🌸 Hi! I’m a feel-good bot. I’ll create a greeting card with art and a caption "
            "for any occasion.\n\nChoose language / Выберите язык:"
        ),
    },
    "choose_occasion": {
        "ru": "🌷 <b>Шаг 1 из 5.</b> Для кого открытка? Выберите кнопку ниже — и мы продолжим вместе.",
        "en": "🌷 <b>Step 1 of 5.</b> Who is the card for? Tap a button below — we’ll go on together.",
    },
    "step1_image": {
        "ru": (
            "🌷 <b>Шаг 2 из 5.</b> Опишите, что должно быть на картинке — текстом или голосом. "
            "Можно написать «придумай сам» — тогда я предложу свою идею."
        ),
        "en": (
            "🌷 <b>Step 2 of 5.</b> Describe what should appear on the image (text or voice). "
            "Or write “surprise me” and I’ll suggest something nice."
        ),
    },
    "step2_holiday": {
        "ru": (
            "🌷 <b>Шаг 3 из 5.</b> Какой праздник или повод? Текстом или голосом.\n\n"
            "<b>Примеры:</b> Новый год, 8 Марта, 1 Мая, день рождения, юбилей, день компании, "
            "профессиональный праздник — или просто «просто так», «для хорошего настроения». Как душе угодно ✨"
        ),
        "en": (
            "🌷 <b>Step 3 of 5.</b> What’s the holiday or occasion? Type or voice.\n\n"
            "<b>Examples:</b> New Year, March 8, May Day, birthday, company day, "
            "a work milestone — or “just because”, “for a good mood”. Whatever feels right ✨"
        ),
    },
    "step3_image_style": {
        "ru": "🌷 <b>Шаг 4 из 5.</b> Выберите стиль картинки — нажмите кнопку:",
        "en": "🌷 <b>Step 4 of 5.</b> Pick an image style — tap a button:",
    },
    "step4_text_style": {
        "ru": "🌷 <b>Шаг 5 из 5.</b> И последнее — стиль текста поздравления:",
        "en": "🌷 <b>Step 5 of 5.</b> Last — the tone of your greeting text:",
    },
    "generating": {
        "ru": "Генерирую открытку… Чуть-чуть терпения ✨",
        "en": "Creating your card… Just a moment ✨",
    },
    "rate_limited": {
        "ru": "Сегодня лимит генераций исчерпан ({limit} в сутки). Загляните завтра!",
        "en": "Daily generation limit reached ({limit} per day). Please try again tomorrow!",
    },
    "maintenance": {
        "ru": "Бот временно недоступен по техническим причинам. Приносим извинения!",
        "en": "The bot is temporarily unavailable. Sorry for the inconvenience!",
    },
    "voice_recognizing": {
        "ru": "Уже слушаю и распознаю голос…",
        "en": "Listening and transcribing…",
    },
    "voice_unavailable": {
        "ru": "Голосовой ввод недоступен: не настроен API распознавания речи.",
        "en": "Voice input is unavailable: speech API is not configured.",
    },
    "err_image": {
        "ru": "Не удалось сгенерировать изображение. Ошибка: {err}",
        "en": "Could not generate the image. Error: {err}",
    },
    "err_text": {
        "ru": "Не удалось сгенерировать текст. Ошибка: {err}",
        "en": "Could not generate the caption. Error: {err}",
    },
    "err_timeout": {
        "ru": "Превышено время ожидания. Попробуйте позже.",
        "en": "Request timed out. Please try again later.",
    },
    "err_generic": {
        "ru": "Произошла ошибка: {err}",
        "en": "Something went wrong: {err}",
    },
    "create_another": {
        "ru": "Создать ещё одну",
        "en": "Create another",
    },
    "regen_repeat": {
        "ru": "Повторить",
        "en": "Repeat",
    },
    "regen_text": {
        "ru": "Другой текст",
        "en": "New caption",
    },
    "regen_image": {
        "ru": "Другая картинка",
        "en": "New image",
    },
    "change_language": {
        "ru": "Сменить язык",
        "en": "Change language",
    },
    "reminder_fallback": {
        "ru": (
            "Я помогаю создавать поздравительные открытки. Отправьте /start, чтобы начать."
        ),
        "en": "I help you create greeting cards. Send /start to begin.",
    },
    "no_saved_card": {
        "ru": "Нет сохранённой открытки. Сначала создайте её через сценарий (/start).",
        "en": "No saved card yet. Create one with /start first.",
    },
    "only_text_voice_step1": {
        "ru": "Опишите картинку текстом или голосовым сообщением (или «придумай сам»).",
        "en": "Describe the image in text or voice (or say “surprise me”).",
    },
    "only_text_voice_step2": {
        "ru": "Напишите повод текстом или голосом (примеры в шаге 3: праздник, «просто так», «для хорошего настроения»).",
        "en": "Type or voice the occasion (see step 3 examples: holiday, “just because”, “good mood”).",
    },
    "empty_image_desc": {
        "ru": "Напишите текстом или отправьте голосовое сообщение: что должно быть на картинке (или «придумай сам»).",
        "en": "Send text or voice: what should appear on the image (or “surprise me”).",
    },
    "empty_holiday": {
        "ru": "Укажите повод: праздник, дата или фраза вроде «просто так» / «для хорошего настроения» — текстом или голосом.",
        "en": "Enter an occasion: a holiday, date, or phrases like “just because” / “for a good mood” (text or voice).",
    },
    "voice_fail": {
        "ru": "Не удалось распознать голос: {err}",
        "en": "Could not transcribe voice: {err}",
    },
    "voice_empty": {
        "ru": "Текст не распознан. Напишите текстом или попробуйте ещё раз голосом.",
        "en": "No text recognized. Please type or try voice again.",
    },
    "voice_dl_fail": {
        "ru": "Не удалось загрузить голосовое сообщение.",
        "en": "Could not download the voice message.",
    },
    "after_voice_holiday": {
        "ru": (
            "Отлично! 🌷 <b>Шаг 3 из 5.</b> Какой праздник или повод? Текстом или голосом.\n"
            "Примеры: Новый год, 8 Марта, 1 Мая, день рождения, юбилей, «просто так», «для хорошего настроения»."
        ),
        "en": (
            "Nice! 🌷 <b>Step 3 of 5.</b> What’s the holiday or occasion? Type or voice.\n"
            "Examples: New Year, March 8, May Day, birthday, “just because”, “for a good mood”."
        ),
    },
    "use_occasion_buttons": {
        "ru": "Сначала выберите, для кого открытка — нажмите одну из кнопок ниже (клиенты, коллеги или близкие).",
        "en": "First tap a button: who the card is for — clients/partners, colleagues, or loved ones.",
    },
    "yandex_env_missing": {
        "ru": (
            "Yandex для текста: в процессе нет YANDEX_API_KEY или YANDEX_FOLDER_ID. "
            "Проверьте env в docker-compose и перезапустите контейнер."
        ),
        "en": (
            "Yandex caption: missing YANDEX_API_KEY or YANDEX_FOLDER_ID in the process env. "
            "Check docker-compose env and restart the container."
        ),
    },
    "after_voice_style": {
        "ru": "Супер! 🌷 <b>Шаг 4 из 5.</b> Выберите стиль картинки — нажмите кнопку:",
        "en": "Lovely! 🌷 <b>Step 4 of 5.</b> Pick an image style — tap a button:",
    },
    "pick_language": {
        "ru": "Выберите язык интерфейса и подписей к открыткам:",
        "en": "Choose the language for the bot and card captions:",
    },
    "lang_saved": {
        "ru": "Язык сохранён. Дальнейшие шаги и подписи будут на выбранном языке.",
        "en": "Language saved. Next steps and captions will use this language.",
    },
    "lang_saved_toast": {
        "ru": "Готово",
        "en": "Done",
    },
    "lang_hint": {
        "ru": "Сменить язык: команда /lang или кнопка под открыткой.",
        "en": "Change language: /lang or the button under your card.",
    },
    "cancel_done": {
        "ru": "Всё сбросили — можно начать с чистого листа. Сначала выберите, для кого открытка.",
        "en": "All cleared — you can start fresh. First choose who the card is for.",
    },
    "cancel_nothing": {
        "ru": "Сейчас нечего отменять. Отправьте /start, чтобы создать открытку.",
        "en": "Nothing to cancel right now. Send /start to create a card.",
    },
    "help_text": {
        "ru": (
            "<b>Команды</b>\n"
            "/start — новая открытка (сброс шагов)\n"
            "/cancel — отменить сценарий и начать заново\n"
            "/lang — русский или English\n"
            "/help — это сообщение\n\n"
            "<b>5 шагов:</b> для кого → идея картинки → повод (можно «просто так») → стиль картинки → стиль текста.\n"
            "После открытки можно повторить, сменить текст или картинку, создать ещё одну, сменить язык.\n"
            "Лимит генераций в сутки (кроме админов)."
        ),
        "en": (
            "<b>Commands</b>\n"
            "/start — new card (resets the wizard)\n"
            "/cancel — cancel and start over\n"
            "/lang — Russian or English\n"
            "/help — this message\n\n"
            "<b>5 steps:</b> who it’s for → image idea → occasion (or “just because”) → image style → text style.\n"
            "After a card: repeat, new caption, new image, another, change language.\n"
            "Daily generation limit (except admins)."
        ),
    },
}


def t(key: str, lang: Lang, **kwargs: object) -> str:
    table = MESSAGES.get(key)
    if not table:
        return key
    template = table.get(lang) or table.get("ru") or key
    if kwargs:
        return template.format(**kwargs)
    return template


def surprise_me_phrases(lang: Lang) -> frozenset[str]:
    if lang == "en":
        return frozenset(
            {
                "surprise me",
                "you choose",
                "anything",
                "random",
            }
        )
    return frozenset(
        {
            "придумай сам",
            "придумай сама",
            "сам",
            "сама",
        }
    )
