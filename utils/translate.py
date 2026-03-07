"""
Simple Russian -> English translation for image prompts.
We don't use external translation API; we pass Russian to prompt or use key phrases.
For production you could add Yandex/Google Translate API here.
"""
import re
from typing import Optional

# Common holidays (Russian -> English) for image prompt
HOLIDAY_TO_EN = {
    "8 марта": "March 8, International Women's Day",
    "8 март": "March 8, International Women's Day",
    "1 мая": "May 1, Labour Day",
    "1 май": "May 1, Labour Day",
    "день рождения": "birthday",
    "новый год": "New Year",
    "начало весны": "beginning of spring",
    "просто так": "just because, festive mood",
    "юбилей": "anniversary",
    "день компании": "company day",
}

# Minimal mapping for common words so image prompt is mostly English
RU_TO_EN = {
    "тюльпаны": "tulips",
    "букет": "bouquet",
    "цветы": "flowers",
    "весна": "spring",
    "праздник": "holiday",
    "открытка": "greeting card",
    "стол": "table",
    "ноутбук": "laptop",
    "офис": "office",
    "солнце": "sun",
    "небо": "sky",
    "сад": "garden",
    "природа": "nature",
    "кофе": "coffee",
    "книга": "book",
    "подарок": "gift",
    "шары": "balloons",
    "конфетти": "confetti",
    "сердечко": "heart",
    "сердечки": "hearts",
    "и": "and",
    "на": "on",
    "в": "in",
    "с": "with",
    "для": "for",
}


def translate_prompt_to_english(russian_text: Optional[str]) -> str:
    """
    Rough translation of user image description to English for ProxiAPI.
    Replaces known Russian words; leaves unknown as-is (model often understands).
    For "придумай сам" or empty, caller should not use this — use auto prompt.
    """
    if not russian_text or not russian_text.strip():
        return ""
    text = russian_text.strip().lower()
    if text in ("придумай сам", "придумай сама", "сам", "сама"):
        return ""
    result = []
    for word in re.findall(r"[а-яёa-z0-9]+|[^\w\s]", text):
        if word in RU_TO_EN:
            result.append(RU_TO_EN[word])
        else:
            result.append(word)
    return " ".join(result).strip() or russian_text


def translate_holiday_to_english(holiday: Optional[str]) -> Optional[str]:
    """Translate holiday name to English for image prompt."""
    if not holiday or not holiday.strip():
        return None
    h = holiday.strip().lower()
    for ru, en in HOLIDAY_TO_EN.items():
        if ru in h:
            return en
    return holiday.strip()
