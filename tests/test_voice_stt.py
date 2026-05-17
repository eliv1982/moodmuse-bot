"""Localized voice STT user messages."""
from services.speech_to_text import SpeechToTextError
from utils.i18n import t
from utils.voice_stt import voice_stt_user_message


def test_technical_error_uses_localized_message_not_raw_provider_text() -> None:
    err = SpeechToTextError(
        "Could not recognize speech. Please try again or type your text.",
        reason="technical",
    )
    msg = voice_stt_user_message("en", err)
    assert msg == t("voice_fail", "en")
    assert "Could not recognize speech" not in msg


def test_russian_technical_error_is_russian() -> None:
    err = SpeechToTextError("OpenAI STT HTTP 500", reason="technical")
    msg = voice_stt_user_message("ru", err)
    assert msg == t("voice_fail", "ru")
    assert "обработать голос" in msg


def test_empty_error_uses_voice_empty_key() -> None:
    err = SpeechToTextError("empty", reason="empty")
    assert voice_stt_user_message("ru", err) == t("voice_empty", "ru")
    assert voice_stt_user_message("en", err) == t("voice_empty", "en")
