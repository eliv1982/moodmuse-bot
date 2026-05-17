"""
Normalize speech-to-text API responses to a plain string.
"""
from __future__ import annotations

import json


def normalize_transcription(raw: str) -> str:
    """
    Return stripped transcription text from a plain or JSON API body.
    Empty string if nothing usable was found.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("text") is not None:
            return str(data["text"]).strip()
    except (json.JSONDecodeError, TypeError):
        pass
    return text
