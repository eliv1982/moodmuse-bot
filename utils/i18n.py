"""
UI strings: Russian / English.
"""
from __future__ import annotations

from typing import Literal

Lang = Literal["ru", "en"]

MESSAGES: dict[str, dict[Lang, str]] = {
    "home_welcome": {
        "ru": (
            "✨ <b>Привет! Я MoodMuse</b> — помогу собрать тёплую открытку: "
            "картинка и подпись под праздник, повод или просто хорошее настроение.\n\n"
            "Нажмите «Создать открытку», когда будете готовы — проведу вас по шагам."
        ),
        "en": (
            "✨ <b>Hi! I’m MoodMuse</b> — I’ll help you make a warm greeting card: "
            "art plus a caption for a holiday, a milestone, or just because.\n\n"
            "Tap <b>Create a card</b> when you’re ready — I’ll guide you step by step."
        ),
    },
    "start_intro": {
        "ru": "🌍 Выберите язык интерфейса и подписей к открыткам:",
        "en": "🌍 Choose the language for the bot and card captions:",
    },
    "btn_create_card": {
        "ru": "🎨 Создать открытку",
        "en": "🎨 Create a card",
    },
    "btn_help_short": {
        "ru": "❓ Помощь",
        "en": "❓ Help",
    },
    "btn_change_lang_short": {
        "ru": "🌍 Язык",
        "en": "🌍 Language",
    },
    "selected_language": {
        "ru": "✅ Выбрано: {label}",
        "en": "✅ Selected: {label}",
    },
    "selected_occasion": {
        "ru": "✅ Для кого: {label}",
        "en": "✅ For: {label}",
    },
    "selected_image_style": {
        "ru": "✅ Стиль картинки: {label}",
        "en": "✅ Image style: {label}",
    },
    "selected_text_style": {
        "ru": "✅ Стиль текста: {label}",
        "en": "✅ Caption style: {label}",
    },
    "lang_saved_friendly": {
        "ru": (
            "Отлично, язык сохранён! 🌷\n"
            "Теперь выберите, для кого открытка — и пойдём дальше."
        ),
        "en": (
            "Great, language saved! 🌷\n"
            "Now pick who the card is for — and we’ll continue."
        ),
    },
    "choose_occasion": {
        "ru": "Для кого открытка? Выберите вариант.",
        "en": "Who is the card for? Pick an option.",
    },
    "image_idea_question": {
        "ru": "Что должно быть на картинке?",
        "en": "What should appear on the image?",
    },
    "btn_image_idea_surprise": {
        "ru": "✨ Придумай сам",
        "en": "✨ Surprise me",
    },
    "btn_image_idea_custom": {
        "ru": "✍️ Особые пожелания",
        "en": "✍️ Custom wishes",
    },
    "btn_image_idea_voice": {
        "ru": "🎙 Голосом",
        "en": "🎙 Voice",
    },
    "image_idea_custom_prompt": {
        "ru": "Напишите текстом, что обязательно должно быть на картинке.",
        "en": "Type what must appear on the image.",
    },
    "image_idea_voice_prompt": {
        "ru": "Отправьте голосовое сообщение с описанием картинки.",
        "en": "Send a voice message describing the image.",
    },
    "image_idea_use_buttons": {
        "ru": "Выберите вариант кнопкой ниже.",
        "en": "Please pick an option using the buttons below.",
    },
    "wizard_small_talk": {
        "ru": (
            "Я здесь 🙂 Сейчас мы собираем открытку. "
            "Ответьте на текущий вопрос или нажмите /cancel, если хотите начать заново."
        ),
        "en": (
            "I’m here 🙂 We’re building your card right now. "
            "Answer the current question or send /cancel to start over."
        ),
    },
    "stale_callback": {
        "ru": "Этот выбор уже неактуален. Начните заново или продолжите текущий сценарий.",
        "en": "This choice is outdated. Start over or continue the current flow.",
    },
    "confirmed_image_idea_auto": {
        "ru": "✅ Идея картинки: придумает MoodMuse",
        "en": "✅ Image idea: MoodMuse will suggest it",
    },
    "summary_image_idea_auto": {
        "ru": "придумает MoodMuse",
        "en": "MoodMuse will suggest it",
    },
    "generation_summary": {
        "ru": (
            "Собрала настройки открытки:\n\n"
            "✅ Для кого: {occasion}\n"
            "✅ Идея картинки: {image_idea}\n"
            "✅ Повод: {holiday}\n"
            "✅ Стиль картинки: {image_style}\n"
            "✅ Стиль текста: {text_style}\n\n"
            "Генерирую открытку… Чуть-чуть терпения ✨"
        ),
        "en": (
            "Here’s your card setup:\n\n"
            "✅ For: {occasion}\n"
            "✅ Image idea: {image_idea}\n"
            "✅ Occasion: {holiday}\n"
            "✅ Image style: {image_style}\n"
            "✅ Caption style: {text_style}\n\n"
            "Creating your card… Just a moment ✨"
        ),
    },
    "step2_holiday": {
        "ru": (
            "Какой праздник или повод? Текстом или голосом.\n\n"
            "<b>Примеры:</b> Новый год, 8 Марта, день рождения, юбилей — "
            "или «просто так», «для хорошего настроения»."
        ),
        "en": (
            "What’s the holiday or occasion? Type or voice.\n\n"
            "<b>Examples:</b> New Year, March 8, birthday, milestone — "
            "or “just because”, “for a good mood”."
        ),
    },
    "step3_image_style": {
        "ru": "Выберите стиль картинки:",
        "en": "Pick an image style:",
    },
    "step4_text_style": {
        "ru": "Выберите стиль текста поздравления:",
        "en": "Pick the tone of your greeting text:",
    },
    "confirmed_image_idea": {
        "ru": "✅ Идея картинки: {text}",
        "en": "✅ Image idea: {text}",
    },
    "confirmed_holiday": {
        "ru": "✅ Повод: {text}",
        "en": "✅ Occasion: {text}",
    },
    "invalid_image_desc": {
        "ru": (
            "Не получилось понять описание. Напишите ещё раз текстом — "
            "например: «щенок на зимней поляне» — или отправьте голосовое."
        ),
        "en": (
            "I couldn’t understand that description. Please type again — "
            "e.g. “puppy on a snowy field” — or send a voice message."
        ),
    },
    "invalid_holiday": {
        "ru": (
            "Не получилось понять повод. Напишите ещё раз — например: «8 Марта», "
            "«день рождения» или «просто так»."
        ),
        "en": (
            "I couldn’t understand the occasion. Please try again — "
            "e.g. “March 8”, “birthday”, or “just because”."
        ),
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
            "Я MoodMuse — делаю открытки с картинкой и подписью. "
            "Нажмите /start или кнопку «Создать открытку»."
        ),
        "en": (
            "I’m MoodMuse — I make cards with art and a caption. "
            "Send /start or tap Create a card."
        ),
    },
    "small_talk_idle": {
        "ru": (
            "Я MoodMuse: помогаю собрать открытку с картинкой и подписью. "
            "Можно начать с кнопки «Создать открытку»."
        ),
        "en": (
            "I’m MoodMuse — I help you make a card with art and a caption. "
            "Tap Create a card to begin."
        ),
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
        "ru": "Напишите повод текстом или голосом (праздник, «просто так», «для хорошего настроения»).",
        "en": "Type or voice the occasion (holiday, “just because”, “for a good mood”).",
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
            "Какой праздник или повод? Текстом или голосом.\n"
            "Примеры: Новый год, 8 Марта, день рождения, «просто так», «для хорошего настроения»."
        ),
        "en": (
            "What’s the holiday or occasion? Type or voice.\n"
            "Examples: New Year, March 8, birthday, “just because”, “for a good mood”."
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
    "text_provider_not_configured": {
        "ru": (
            "Провайдер генерации текста не настроен. "
            "Укажите OPENAI_API_KEY в .env (TEXT_PROVIDER=openai) и перезапустите бота."
        ),
        "en": (
            "Text generation provider is not configured. "
            "Set OPENAI_API_KEY in .env (TEXT_PROVIDER=openai) and restart the bot."
        ),
    },
    "image_proxi_not_configured": {
        "ru": (
            "Генерация изображений недоступна: укажите PROXI_API_KEY в .env "
            "(IMAGE_PROVIDER=proxi) и перезапустите бота."
        ),
        "en": (
            "Image generation is not configured: set PROXI_API_KEY in .env "
            "(IMAGE_PROVIDER=proxi) and restart the bot."
        ),
    },
    "image_provider_not_configured": {
        "ru": (
            "Провайдер генерации изображений не настроен. "
            "Укажите OPENAI_API_KEY в .env (IMAGE_PROVIDER=openai) и перезапустите бота."
        ),
        "en": (
            "Image generation provider is not configured. "
            "Set OPENAI_API_KEY in .env (IMAGE_PROVIDER=openai) and restart the bot."
        ),
    },
    "after_voice_style": {
        "ru": "Выберите стиль картинки:",
        "en": "Pick an image style:",
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
        "ru": "Сценарий отменён. Можно начать заново с главного меню.",
        "en": "Wizard cancelled. You can start again from the home menu.",
    },
    "cancel_nothing": {
        "ru": "Сейчас нечего отменять. Отправьте /start — откроется главное меню.",
        "en": "Nothing to cancel. Send /start for the home menu.",
    },
    "help_text": {
        "ru": (
            "<b>MoodMuse</b> — бот для тёплых открыток: картинка и подпись под праздник или повод.\n\n"
            "<b>Создание открытки</b>\n"
            "1) для кого (клиенты, коллеги, близкие)\n"
            "2) идея картинки: «Придумай сам» или особые пожелания\n"
            "3) праздник или повод (можно «просто так»)\n"
            "4) стиль картинки\n"
            "5) стиль текста\n\n"
            "<b>Команды</b>\n"
            "/start — главное меню\n"
            "/cancel — отменить и вернуться в меню\n"
            "/lang — язык интерфейса\n"
            "/help — эта справка\n\n"
            "После генерации можно повторить открытку, сменить текст или картинку.\n"
            "Голосовой ввод зависит от настройки распознавания речи (ProxyAPI).\n"
            "Лимит генераций в сутки (кроме админов)."
        ),
        "en": (
            "<b>MoodMuse</b> makes warm greeting cards: art plus a caption for any occasion.\n\n"
            "<b>Creating a card</b>\n"
            "1) who it’s for (clients, colleagues, loved ones)\n"
            "2) image idea: Surprise me or custom wishes\n"
            "3) holiday or occasion (“just because” is fine)\n"
            "4) image style\n"
            "5) caption style\n\n"
            "<b>Commands</b>\n"
            "/start — home menu\n"
            "/cancel — cancel and return to menu\n"
            "/lang — interface language\n"
            "/help — this message\n\n"
            "After a card you can repeat it, change the caption or image.\n"
            "Voice input depends on speech recognition (ProxyAPI).\n"
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
