"""
Prompt builders for image (ProxiAPI, English) and text (YandexGPT, RU/EN).
"""
from typing import Optional

from utils.i18n import Lang

# Occasion types (callback data) and button labels
OCCASION_CLIENTS = "occasion_clients"
OCCASION_COLLEAGUES = "occasion_colleagues"
OCCASION_LOVED = "occasion_loved"

OCCASION_LABELS = {
    OCCASION_CLIENTS: ("Для клиентов/партнёров 🏢", "Clients / partners 🏢"),
    OCCASION_COLLEAGUES: ("Для коллег 👥", "Colleagues 👥"),
    OCCASION_LOVED: ("Для близких ❤️", "Loved ones ❤️"),
}

# Exactly 8 visible image styles in the wizard keyboard (2 columns × 4 rows).
IMAGE_STYLE_KEYBOARD_ORDER = (
    "style_realistic",
    "style_fantasy",
    "style_cyberpunk",
    "style_watercolor",
    "style_cartoon",
    "style_cinematic",
    "style_minimal",
    "style_botanical",
)

_FANTASY_PROMPT = "fantasy art, magical, fairy tale, dragons, elves, epic illustration"

IMAGE_STYLES = {
    "style_realistic": "realistic, photorealistic, high detail",
    "style_fantasy": _FANTASY_PROMPT,
    "style_cyberpunk": "cyberpunk, neon lights, futuristic sci-fi, glowing accents, night city",
    "style_watercolor": "watercolor greeting card, soft brush, artistic painting, delicate washes",
    "style_cartoon": "cozy warm illustration, soft lighting, hygge mood, gentle welcoming details",
    "style_cinematic": "cinematic, movie still, dramatic lighting, film look, widescreen composition",
    "style_minimal": "minimalist, clean, simple shapes, flat design",
    "style_botanical": "vintage botanical illustration, antique natural history, detailed flora, aged paper",
    # Legacy keys (regen / saved cards) — kept off the keyboard
    "style_humor": "humorous, caricature, funny cartoon style",
    "style_vintage": "vintage, retro, nostalgic, classic",
    "style_3d": "3D render, modern CGI, smooth lighting",
    "style_oil": "oil painting, impasto, rich brushstrokes, classical fine art",
    "style_fantasy_art": _FANTASY_PROMPT,
}

IMAGE_STYLE_LABELS = {
    "style_realistic": ("🖼 Реалистичный", "🖼 Realistic"),
    "style_fantasy": ("🐉 Фэнтези", "🐉 Fantasy"),
    "style_cyberpunk": ("🌃 Киберпанк / неоновая фантастика", "🌃 Cyberpunk / neon sci-fi"),
    "style_watercolor": ("🎨 Акварельная открытка", "🎨 Watercolor card"),
    "style_cartoon": ("🕯 Уютная иллюстрация", "🕯 Cozy illustration"),
    "style_cinematic": ("🎬 Кинематографичный", "🎬 Cinematic"),
    "style_minimal": ("✨ Минималистичный", "✨ Minimalist"),
    "style_botanical": ("🌿 Винтажная ботаника", "🌿 Vintage botanical"),
    # Legacy (not shown in keyboard)
    "style_humor": ("С юмором/карикатура", "Humor / caricature"),
    "style_vintage": ("Винтаж/ретро", "Vintage / retro"),
    "style_3d": ("3D-рендер", "3D render"),
    "style_oil": ("Масляные краски", "Oil painting"),
    "style_fantasy_art": ("Фэнтези", "Fantasy art"),
}

TEXT_STYLES = {
    "text_business": (
        "деловой, официальный, уважительный",
        "professional, respectful, business-appropriate",
    ),
    "text_warm": (
        "душевный, лирический, тёплый",
        "warm, heartfelt, lyrical",
    ),
    "text_poetry": (
        "в стихах: обязательно рифма, чёткий ритм, 2–4 строки или четверостишие",
        "in verse: clear rhyme and rhythm, 2–4 lines or a quatrain",
    ),
    "text_humor": (
        "с юмором, лёгкий, дружеский",
        "light humor, friendly tone",
    ),
    "text_short": (
        "очень кратко, одно-два предложения, по делу",
        "very brief, one or two sentences",
    ),
    "text_formal": (
        "формальный, нейтральный, без лишних эмоций",
        "formal, neutral, restrained",
    ),
    "text_emotional": (
        "эмоциональный, тёплый, с пожеланиями от души",
        "emotional, warm, sincere wishes",
    ),
}

TEXT_STYLE_LABELS = {
    "text_business": ("Деловой", "Business"),
    "text_warm": ("Душевный/лирический", "Warm / lyrical"),
    "text_poetry": ("Стихи (в рифму)", "Poetry (rhymed)"),
    "text_humor": ("С юмором 😂", "Humor 😂"),
    "text_short": ("Кратко", "Short"),
    "text_formal": ("Формальный", "Formal"),
    "text_emotional": ("Эмоциональный", "Emotional"),
}

TEXT_STYLE_CALLBACKS = frozenset(TEXT_STYLE_LABELS.keys())
IMAGE_STYLE_CALLBACKS = frozenset(IMAGE_STYLE_LABELS.keys())

_RECIPIENT_IMAGE_HINTS = {
    OCCASION_CLIENTS: (
        "professional, respectful, suitable for clients and partners; "
        "avoid romantic intimacy, avoid heart motifs unless explicitly requested"
    ),
    OCCASION_COLLEAGUES: (
        "friendly workplace-appropriate mood, not overly personal; "
        "tasteful light humor is fine if the style allows"
    ),
    OCCASION_LOVED: (
        "warm, personal, emotional, affectionate atmosphere is welcome"
    ),
}


def build_image_prompt(
    occasion: str,
    image_style_key: str,
    user_description: Optional[str] = None,
    holiday: Optional[str] = None,
    surprise_phrases: Optional[set[str]] = None,
) -> str:
    """
    Build English prompt for ProxiAPI image generation.
    If user_description is empty or "surprise me", generate generic festive card prompt.
    """
    style_phrase = IMAGE_STYLES.get(image_style_key, "beautiful, festive")
    holiday_part = f" for {holiday}" if holiday else ""
    phrases = surprise_phrases or {
        "",
        "придумай сам",
        "придумай сама",
        "surprise me",
        "you choose",
    }

    desc = (user_description or "").strip().lower()
    if user_description and desc not in phrases:
        base = user_description.strip()
    else:
        base = f"Beautiful festive greeting card{holiday_part}, warm mood"

    audience = _RECIPIENT_IMAGE_HINTS.get(occasion, "appropriate, tasteful greeting card mood")
    return f"{base}, {style_phrase}, {audience}, greeting card design, no text on image".strip()


def build_text_system_prompt(occasion: str, text_style_key: str, lang: Lang) -> str:
    """System prompt for YandexGPT."""
    style_pair = TEXT_STYLES.get(text_style_key, ("тёплый и уместный", "warm and fitting"))
    style_desc = style_pair[1] if lang == "en" else style_pair[0]

    if lang == "en":
        occasion_hint = {
            OCCASION_CLIENTS: (
                "Audience: clients or partners — neutral, professional, respectful; "
                "no romantic tone or heart symbols unless the user explicitly asked."
            ),
            OCCASION_COLLEAGUES: (
                "Audience: colleagues — friendly and human, not too personal; "
                "light humor is fine if the caption style is humorous."
            ),
            OCCASION_LOVED: (
                "Audience: loved ones — warmer, more personal and emotional."
            ),
        }.get(occasion, "General greeting.")
        base = (
            f"You write short greeting card captions. Avoid clichés. Style: {style_desc}. {occasion_hint} "
        )
        if text_style_key == "text_poetry":
            base += (
                "Use clear rhyme and steady rhythm (e.g. AABB or ABAB). "
                "Write a quatrain or 2–4 lines. Poetry must rhyme."
            )
        else:
            base += "One short paragraph only."
    else:
        occasion_hint = {
            OCCASION_CLIENTS: (
                "Обращение к клиентам или партнёрам: нейтрально, уважительно, деловой тон; "
                "без романтики и без «сердечек», если пользователь сам этого не просил."
            ),
            OCCASION_COLLEAGUES: (
                "Обращение к коллегам: дружелюбно, по-человечески, но не слишком лично; "
                "лёгкий юмор уместен, если выбран юмористический стиль."
            ),
            OCCASION_LOVED: (
                "Обращение к близким: теплее, личнее, эмоциональнее, от души."
            ),
        }.get(occasion, "Универсальное поздравление.")
        base = (
            f"Ты — автор коротких поздравлений на русском. "
            f"Стиль: {style_desc}. {occasion_hint} "
            "Пиши естественным современным русским, как живая речь: без канцелярита и без кальки с английского. "
            "Не используй неловкие обращения вроде «Солнечному тебе дню» — говори нормально: «Солнечного дня», «Желаю солнечного настроения» и т.п. "
            "Не нагромождай в одном тексте много разных метафор подряд (радуга, облачко, смех ребёнка) — достаточно одного образа или ни одного. "
            "Избегай штампов вроде «пусть сбудутся мечты» без конкретики; без лишних восклицаний."
        )
        if text_style_key == "text_poetry":
            base += (
                " Стихи обязаны быть в рифму: парная (ААББ) или перекрёстная (АБАБ), "
                "соблюдай ритм. Четверостишие или 2–4 строки."
            )
        else:
            base += " Один короткий абзац, 2–4 предложения."

    return base


def build_text_user_prompt(holiday: Optional[str], lang: Lang) -> str:
    if lang == "en":
        holiday_part = f"Occasion: {holiday}." if holiday else "Occasion: general greeting."
        return (
            f"Write the greeting caption only. {holiday_part} "
            "Output only the greeting text, no title or meta."
        )
    holiday_part = f"Праздник/повод: {holiday}." if holiday else "Повод: общее поздравление."
    return (
        f"Напиши только текст поздравления. {holiday_part} "
        "Без заголовка, без «С уважением», без пояснений и вопросов к адресату."
    )


def image_variation_suffix() -> str:
    """Append for 'new image' regen to encourage diversity."""
    return "alternative composition, fresh details, varied layout, same theme and mood"
