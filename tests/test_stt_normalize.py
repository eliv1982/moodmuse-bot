"""STT response normalization."""
from services.providers.stt_normalize import normalize_transcription


def test_normalize_plain_text() -> None:
    assert normalize_transcription("  Hello world  ") == "Hello world"


def test_normalize_json_text_field() -> None:
    assert normalize_transcription('{"text": "  Привет  "}') == "Привет"


def test_normalize_empty() -> None:
    assert normalize_transcription("") == ""
    assert normalize_transcription('{"text": ""}') == ""
