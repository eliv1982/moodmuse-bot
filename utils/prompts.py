"""
Prompt builders for image (ProxiAPI, English) and text (GigaChat, Russian).
"""
from typing import Optional

# Occasion types (callback data) and button labels
OCCASION_CLIENTS = "occasion_clients"
OCCASION_COLLEAGUES = "occasion_colleagues"
OCCASION_LOVED = "occasion_loved"

OCCASION_LABELS = {
    OCCASION_CLIENTS: "Для клиентов/партнёров 🏢",
    OCCASION_COLLEAGUES: "Для коллег 👥",
    OCCASION_LOVED: "Для близких ❤️",
}

# Image style callback -> English label for prompt; button label
IMAGE_STYLES = {
    "style_realistic": "realistic, photorealistic, high detail",
    "style_cartoon": "cartoon, animated, friendly illustration",
    "style_humor": "humorous, caricature, funny cartoon style",
    "style_fantasy": "fantasy, cyberpunk, sci-fi, futuristic",
    "style_minimal": "minimalist, clean, simple shapes, flat design",
    "style_vintage": "vintage, retro, nostalgic, classic",
    "style_watercolor": "watercolor, soft brush, artistic painting",
    "style_3d": "3D render, modern CGI, smooth lighting",
    "style_botanical": "botanical illustration, natural history, detailed flora",
    "style_oil": "oil painting, impasto, rich brushstrokes, classical fine art",
    "style_fantasy_art": "fantasy art, magical, fairy tale, dragons, elves, epic illustration",
    "style_cinematic": "cinematic, movie still, dramatic lighting, film look, widescreen composition",
}

IMAGE_STYLE_LABELS = {
    "style_realistic": "Реалистичный",
    "style_cartoon": "Мультяшный",
    "style_humor": "С юмором/карикатура",
    "style_fantasy": "Фантастический/киберпанк",
    "style_minimal": "Минимализм",
    "style_vintage": "Винтаж/ретро",
    "style_watercolor": "Акварель",
    "style_3d": "3D-рендер",
    "style_botanical": "Ботаническая иллюстрация",
    "style_oil": "Масляные краски",
    "style_fantasy_art": "Фэнтези",
    "style_cinematic": "Кинематографический",
}

# Text style callback -> description for GigaChat; button label
TEXT_STYLES = {
    "text_business": "деловой, официальный, уважительный",
    "text_warm": "душевный, лирический, тёплый",
    "text_poetry": "в стихах: обязательно рифма (парная или перекрёстная), чёткий ритм, 2–4 строки или четверостишие",
    "text_humor": "с юмором, лёгкий, дружеский",
    "text_short": "очень кратко, одно-два предложения, по делу",
    "text_formal": "формальный, нейтральный, без лишних эмоций",
    "text_emotional": "эмоциональный, тёплый, с пожеланиями от души",
}

TEXT_STYLE_LABELS = {
    "text_business": "Деловой",
    "text_warm": "Душевный/лирический",
    "text_poetry": "Стихи (в рифму)",
    "text_humor": "С юмором",
    "text_short": "Кратко",
    "text_formal": "Формальный",
    "text_emotional": "Эмоциональный",
}


def build_image_prompt(
    occasion: str,
    image_style_key: str,
    user_description: Optional[str] = None,
    holiday: Optional[str] = None,
) -> str:
    """
    Build English prompt for ProxiAPI image generation.
    If user_description is empty or "придумай сам", generate generic spring card prompt.
    """
    style_phrase = IMAGE_STYLES.get(image_style_key, "beautiful, festive")
    holiday_part = f" for {holiday}" if holiday else ""

    if user_description and user_description.strip().lower() not in (
        "",
        "придумай сам",
        "придумай сама",
    ):
        # User provided description — use it (assumed already in English from translator)
        base = user_description.strip()
    else:
        # Auto-generated: festive card for the occasion (any holiday)
        base = f"Beautiful festive greeting card{holiday_part}, warm mood"

    return f"{base}, {style_phrase}, greeting card design, no text on image".strip()


def build_text_system_prompt(occasion: str, text_style_key: str) -> str:
    """System prompt for GigaChat: tone and style."""
    style_desc = TEXT_STYLES.get(text_style_key, "тёплый и уместный")
    occasion_hint = {
        OCCASION_CLIENTS: "Обращение к клиентам или партнёрам: уважительно, профессионально.",
        OCCASION_COLLEAGUES: "Обращение к коллегам: дружелюбно, по-человечески.",
        OCCASION_LOVED: "Обращение к близким: от души, лично, тёпло.",
    }.get(occasion, "Универсальное поздравление.")

    base = (
        f"Ты — автор поздравительных текстов. Пиши кратко, без клише, от души. "
        f"Стиль текста: {style_desc}. {occasion_hint} "
        "Не используй шаблонные фразы."
    )
    if text_style_key == "text_poetry":
        base += (
            " Стихи обязаны быть в рифму: используй парную (ААББ) или перекрёстную (АБАБ) рифмовку, "
            "соблюдай ритм (например, 4–5 стоп ямба или хорея). Пиши четверостишие или 2–4 строки. Без рифмы не принимается."
        )
    else:
        base += " Один короткий абзац."
    return base


def build_text_user_prompt(holiday: Optional[str], occasion: str) -> str:
    """User prompt for GigaChat: occasion and holiday."""
    holiday_part = f"Праздник/повод: {holiday}." if holiday else "Повод: общее поздравление."
    return (
        f"Напиши текст поздравления. {holiday_part} "
        "Только текст поздравления, без подписи и пояснений."
    )
