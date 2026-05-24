"""
Wizard personalization fields: recipient address and sender signature.
"""
from __future__ import annotations

import re
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import Lang, t

RECIPIENT_ADDRESS_MAX_LEN = 80
SIGNATURE_MAX_LEN = 80

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_JSONISH_RE = re.compile(r"[\{\}\[\]]|\"[\w]+\":")

WIZARD_RECIPIENT_YES = "wizard:recipient:yes"
WIZARD_RECIPIENT_NO = "wizard:recipient:no"
WIZARD_SIGNATURE_YES = "wizard:signature:yes"
WIZARD_SIGNATURE_NO = "wizard:signature:no"

WIZARD_PERSONALIZATION_CALLBACKS = frozenset(
    {
        WIZARD_RECIPIENT_YES,
        WIZARD_RECIPIENT_NO,
        WIZARD_SIGNATURE_YES,
        WIZARD_SIGNATURE_NO,
    }
)


def _normalize_one_line(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def _validate_short_phrase(raw: str, *, max_len: int) -> Optional[str]:
    if "\n" in (raw or "") or "\r" in (raw or ""):
        return None
    text = _normalize_one_line(raw)
    if not text or len(text) > max_len:
        return None
    if _CONTROL_CHARS_RE.search(text):
        return None
    if _URL_RE.search(text) or _JSONISH_RE.search(text):
        return None
    if not any(c.isalnum() for c in text):
        return None
    weird = sum(
        1
        for c in text
        if not c.isalnum() and not c.isspace() and c not in ",'-.!?«»\"—–"
    )
    if weird > 10:
        return None
    return text


def validate_recipient_address(raw: str) -> Optional[str]:
    """Greeting/address phrase — name or short phrase, up to 80 chars."""
    return _validate_short_phrase(raw, max_len=RECIPIENT_ADDRESS_MAX_LEN)


def validate_sender_signature(raw: str) -> Optional[str]:
    return _validate_short_phrase(raw, max_len=SIGNATURE_MAX_LEN)


def build_personalization_prompt_suffix(
    recipient_address: Optional[str],
    sender_signature: Optional[str],
    lang: Lang,
) -> str:
    """Soft instructions for caption generation (does not override profile prefs)."""
    parts: list[str] = []
    if recipient_address and recipient_address.strip():
        addr = recipient_address.strip()
        if lang == "en":
            parts.append(
                f"CARD ADDRESSEE (required): {addr}. "
                "Open the caption with this greeting/address, keeping the user's exact wording. "
                "It may be a name or a phrase — do not assume it is a personal name. "
                "Do NOT use the bot user's profile name as the addressee when this field is set."
            )
        else:
            parts.append(
                f"АДРЕСАТ ОТКРЫТКИ (обязательно): {addr}. "
                "Начни текст с этого обращения, сохраняя формулировку пользователя. "
                "Это может быть имя или фраза — не считай, что это обязательно личное имя. "
                "НЕ используй имя из профиля пользователя бота как адресата, если задано это поле."
            )
    if sender_signature and sender_signature.strip():
        sig = sender_signature.strip()
        if lang == "en":
            parts.append(
                f"If appropriate, end the caption with a closing signature close to: {sig}. "
                "Keep the signature wording and tone."
            )
        else:
            parts.append(
                f"Если уместно, заверши текст подписью, близкой по смыслу к: {sig}. "
                "Сохрани формулировку и тон подписи."
            )
    if not parts:
        return ""
    return " ".join(parts)


def recipient_toggle_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_wizard_yes", lang), callback_data=WIZARD_RECIPIENT_YES
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_wizard_no", lang), callback_data=WIZARD_RECIPIENT_NO
                )
            ],
        ]
    )


def signature_toggle_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_wizard_yes", lang), callback_data=WIZARD_SIGNATURE_YES
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_wizard_no", lang), callback_data=WIZARD_SIGNATURE_NO
                )
            ],
        ]
    )
