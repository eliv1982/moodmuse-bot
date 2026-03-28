"""
Holiday / prompt normalization for image prompts (English output for ProxiAPI).
"""
import re
from typing import Optional

from utils.i18n import Lang

# Russian holidays -> English fragments for image prompt
HOLIDAY_TO_EN = {
    "8 марта": "March 8, International Women's Day",
    "8 март": "March 8, International Women's Day",
    "1 мая": "May 1, Labour Day",
    "1 май": "May 1, Labour Day",
    "день рождения": "birthday",
    "новый год": "New Year",
    "начало весны": "beginning of spring",
    "просто так": "just because, festive mood",
    "для хорошего настроения": "good mood, cheerful greeting, positive vibes",
    "хорошего настроения": "good mood, cheerful greeting",
    "юбилей": "anniversary",
    "день компании": "company day",
}

# English phrases -> canonical English (optional enrichment)
HOLIDAY_EN_CANON = {
    "women's day": "March 8, International Women's Day",
    "international women's day": "March 8, International Women's Day",
    "new year": "New Year",
    "birthday": "birthday",
    "labor day": "May 1, Labour Day",
    "labour day": "May 1, Labour Day",
    "may day": "May 1, Labour Day",
}

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


def translate_prompt_to_english(text: Optional[str], lang: Lang) -> str:
    """
    For RU: replace known words. For EN: return cleaned text as-is.
    """
    if not text or not text.strip():
        return ""
    if lang == "en":
        return text.strip()
    t = text.strip().lower()
    if t in ("придумай сам", "придумай сама", "сам", "сама"):
        return ""
    result = []
    for word in re.findall(r"[а-яёa-z0-9]+|[^\w\s]", t):
        if word in RU_TO_EN:
            result.append(RU_TO_EN[word])
        else:
            result.append(word)
    return " ".join(result).strip() or text.strip()


def translate_holiday_to_english(holiday: Optional[str], lang: Lang) -> Optional[str]:
    if not holiday or not holiday.strip():
        return None
    h = holiday.strip()
    low = h.lower()
    if lang == "en":
        for en_key, canon in HOLIDAY_EN_CANON.items():
            if en_key in low:
                return canon
        return h.strip()
    for ru, en in HOLIDAY_TO_EN.items():
        if ru in low:
            return en
    return h.strip()
