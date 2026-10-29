"""
Exact inscriptions at the renderer: what ``check_inscription`` accepts is drawn whole and unaltered (the
ellipsis shortening that protects AI phrases never applies to it), unsupported characters are refused up
front rather than drawn as boxes, and explicit line breaks are kept.
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from services import card_render
from services.card_render import (
    INSCRIPTION_MAX_CHARS,
    MARGIN_X,
    MAX_BLOCK_HEIGHT,
    MAX_FONT,
    MIN_FONT,
    check_inscription,
    draw_short_text,
    fit_text,
    render_card_image,
    wrap_text,
    _font,
)

ACCEPTED = [
    "С днём рождения!",
    "Мама, я тебя люблю",
    "«Люблю» — навсегда.",
    "Happy birthday, Mom!",
    "С 8 Марта!\nСчастья, здоровья и тепла",
    "Ёлка, ёж и № 5 за 100 €",
    "Дорогая бабушка, спасибо тебе за всё, что ты для нас делаешь каждый день",
    "а",
]


def png(size: int = 512) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (200, 180, 160)).save(buf, format="PNG")
    return buf.getvalue()


def nominal_fit(text: str):
    return fit_text(
        text,
        round(1024 * (1 - 2 * MARGIN_X)),
        round(1024 * MAX_BLOCK_HEIGHT),
        round(1024 * MAX_FONT),
        round(1024 * MIN_FONT),
    )


@pytest.mark.parametrize("text", ACCEPTED)
def test_accepted_inscriptions_fit_whole(text: str) -> None:
    assert check_inscription(text).ok
    fitted = nominal_fit(text)
    assert fitted.truncated is False
    assert "…" not in "".join(fitted.lines) or "…" in text
    assert "".join("".join(fitted.lines).split()) == "".join(text.split()), "every word is drawn, none added"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "empty"),
        ("   \n  ", "empty"),
        ("а" * (INSCRIPTION_MAX_CHARS + 1), "too_long"),
        ("Ш" * INSCRIPTION_MAX_CHARS, "does_not_fit"),
        ("С днём рождения 🎂", "unsupported"),
        ("Люблю ❤", "unsupported"),
        ("日本語", "unsupported"),
    ],
)
def test_refused_inscriptions_say_why(text: str, reason: str) -> None:
    check = check_inscription(text)
    assert not check.ok and check.reason == reason


def test_unsupported_characters_are_reported_so_the_user_can_remove_them() -> None:
    check = check_inscription("Привет 🎂 и ❤")
    assert check.reason == "unsupported"
    assert set(check.detail) == {"🎂", "❤"}


def test_anything_refused_for_length_would_otherwise_be_shortened_with_an_ellipsis() -> None:
    text = "Ш" * INSCRIPTION_MAX_CHARS
    assert not check_inscription(text).ok
    assert nominal_fit(text).truncated is True, "this is exactly the silent rewrite the check prevents"


def test_the_limit_is_stated_in_characters_not_lines() -> None:
    assert check_inscription("а " * (INSCRIPTION_MAX_CHARS // 2)).ok


def test_explicit_line_breaks_are_kept_as_separate_lines() -> None:
    font = _font(40)
    assert wrap_text("Раз два\nтри четыре", font, 10_000) == ["Раз два", "три четыре"]
    assert wrap_text("Раз\n\n\nдва", font, 10_000) == ["Раз", "два"], "blank lines collapse, text is kept"


def test_text_without_line_breaks_wraps_as_before() -> None:
    font = _font(40)
    lines = wrap_text("слово " * 30, font, 400)
    assert len(lines) > 1 and " ".join(lines).split() == ["слово"] * 30


def test_a_multi_line_inscription_is_drawn_on_the_image() -> None:
    drawn = draw_short_text(png(), "С 8 Марта!\nСчастья и тепла")
    assert Image.open(io.BytesIO(drawn)).size == (512, 512)
    assert drawn != png()


async def test_the_renderer_receives_the_exact_text_not_a_cleaned_copy() -> None:
    exact = "  «Люблю» — навсегда!  "  # quotes and edge spaces are not for the cleaner to strip
    with patch.object(card_render, "draw_short_text", MagicMock(return_value=b"DRAWN")) as draw:
        image, drawn = await render_card_image(png(), exact)

    assert (image, drawn) == (b"DRAWN", True)
    assert draw.call_args.args[1] == exact.strip()


async def test_an_empty_inscription_leaves_the_image_untouched() -> None:
    original = png()
    with patch.object(card_render, "draw_short_text", MagicMock()) as draw:
        image, drawn = await render_card_image(original, "")

    assert (image, drawn) == (original, False) and not draw.called
