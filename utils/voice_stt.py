"""Voice STT helpers for handlers (localized user messages)."""
from __future__ import annotations

from services.speech_to_text import SpeechToTextError
from utils.i18n import Lang, t


def voice_stt_user_message(lang: Lang, err: SpeechToTextError) -> str:
    """Map STT errors to localized user-facing text (no raw provider messages)."""
    if err.reason == "empty":
        return t("voice_empty", lang)
    return t("voice_fail", lang)
