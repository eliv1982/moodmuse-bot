"""Caption truncation for Telegram."""
from services.card_generation import caption_for_telegram_html, truncate_caption


def test_truncate_short() -> None:
    assert truncate_caption("hello", 1024) == "hello"


def test_truncate_long() -> None:
    s = "a" * 2000
    out = truncate_caption(s, 1024)
    assert len(out) == 1024
    assert out.endswith("…")


def test_caption_escapes_html() -> None:
    raw = "<b>Hi</b> & you"
    out = caption_for_telegram_html(raw, 100)
    assert "&lt;b&gt;Hi&lt;/b&gt; &amp; you" == out
