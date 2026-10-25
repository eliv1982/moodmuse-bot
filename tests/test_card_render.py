"""Embedded-phrase rendering: fonts, fitting, contrast, fallback and not blocking the event loop."""
from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from services import card_render
from services.card_render import (
    ELLIPSIS,
    FONT_PATH,
    MARGIN_X,
    MAX_BLOCK_HEIGHT,
    MAX_FONT,
    MAX_LINES,
    MIN_FONT,
    SCRIM_ALPHA,
    draw_short_text,
    fit_text,
    render_card_image,
    wrap_text,
)

RU = "С днём рождения! Пусть сбываются самые тёплые желания"
EN = "Wishing you a day as bright as your smile"
SIZE = 1024


def _png(color: tuple[int, int, int] = (90, 120, 160), size: tuple[int, int] = (SIZE, SIZE), mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, color if mode == "RGB" else None).save(buf, format="PNG")
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _box(size: int = SIZE) -> tuple[int, int, int, int]:
    """(box_width, box_height, max_font, min_font) the renderer derives for a square image."""
    return (
        round(size * (1 - 2 * MARGIN_X)),
        round(size * MAX_BLOCK_HEIGHT),
        round(size * MAX_FONT),
        round(size * MIN_FONT),
    )


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _bright_pixels(img: Image.Image, top: int, bottom: int) -> int:
    region = img.crop((0, top, img.width, bottom)).convert("L")
    return sum(region.histogram()[236:])


# ----- font -----


def test_bundled_font_and_its_license_ship_together() -> None:
    assert FONT_PATH.is_file()
    licence = (FONT_PATH.parent / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    assert (Path(card_render.__file__).resolve().parent.parent / "assets" / "fonts").is_dir()


def test_font_has_real_glyphs_for_cyrillic_and_latin() -> None:
    font = card_render._font(64)

    def glyph(ch: str) -> bytes:
        img = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(img).text((10, 10), ch, font=font, fill=255)
        return img.tobytes()

    notdef = glyph("\U0010FFFF")
    for ch in "АЯЖЁабвгдёжяABCxyz":
        assert glyph(ch) != notdef, f"{ch!r} renders as the missing-glyph box"
    assert glyph("Ж") != glyph("Ш")


# ----- rendering -----


@pytest.mark.parametrize("text", [RU, EN], ids=["cyrillic", "latin"])
def test_phrase_is_drawn_near_the_bottom_and_the_top_is_untouched(text: str) -> None:
    original = _png((20, 20, 30))
    out = _open(draw_short_text(original, text))

    assert out.size == (SIZE, SIZE)
    assert out.getpixel((SIZE // 2, 5)) == (20, 20, 30)  # nothing above the scrim
    assert _bright_pixels(out, int(SIZE * 0.55), SIZE) > 400  # glyph pixels exist
    assert _bright_pixels(out, 0, int(SIZE * 0.4)) == 0


def test_cyrillic_and_latin_do_not_render_as_missing_glyph_boxes() -> None:
    original = _png((20, 20, 30))
    cyr = draw_short_text(original, "ЖЖЖЖ ШШШШ")
    tofu = draw_short_text(original, "\U0010FFFF\U0010FFFF\U0010FFFF\U0010FFFF")
    assert cyr != tofu
    assert draw_short_text(original, "Жук") != draw_short_text(original, "Шум")


def test_the_original_bytes_are_not_modified() -> None:
    original = _png()
    snapshot = bytes(original)
    rendered = draw_short_text(original, RU)
    assert original == snapshot
    assert rendered != original


def test_white_text_keeps_aaa_contrast_even_on_a_pure_white_image() -> None:
    out = _open(draw_short_text(_png((255, 255, 255)), RU))
    # A pixel in the left margin at text height shows the scrim alone, with no glyph on it.
    backdrop = out.getpixel((10, SIZE - 100))
    assert backdrop[0] == pytest.approx(255 * (1 - SCRIM_ALPHA), abs=2)
    assert _contrast((255, 255, 255), backdrop) >= 7.0


def test_text_stays_inside_the_horizontal_margins() -> None:
    out = _open(draw_short_text(_png((0, 0, 0)), "W" * 80 + " " + "Ж" * 5))
    margin = int(SIZE * MARGIN_X) - 2
    left = _bright_pixels(out.crop((0, 0, margin, SIZE)), 0, SIZE)
    right = _bright_pixels(out.crop((SIZE - margin, 0, SIZE, SIZE)), 0, SIZE)
    assert left == 0 and right == 0


@pytest.mark.parametrize("size", [(64, 64), (300, 500), (1536, 1024), (1024, 1536), (2048, 2048)])
def test_any_image_size_renders_with_the_text_in_bounds(size: tuple[int, int]) -> None:
    out = _open(draw_short_text(_png((10, 10, 10), size), RU))
    assert out.size == size


@pytest.mark.parametrize("mode", ["RGBA", "L", "P", "CMYK"])
def test_other_color_modes_are_accepted(mode: str) -> None:
    buf = io.BytesIO()
    Image.new(mode, (256, 256)).save(buf, format="PNG" if mode != "CMYK" else "TIFF")
    assert _open(draw_short_text(buf.getvalue(), EN)).size == (256, 256)


def test_output_is_a_png() -> None:
    assert draw_short_text(_png(), EN).startswith(b"\x89PNG\r\n\x1a\n")


# ----- fitting -----


def test_short_text_gets_the_largest_font_on_few_lines() -> None:
    box_w, box_h, max_size, min_size = _box()
    fitted = fit_text("Happy birthday", box_w, box_h, max_size, min_size)
    assert fitted.size == max_size
    assert not fitted.truncated
    assert len(fitted.lines) <= 2


def test_long_text_shrinks_to_fit_without_truncation() -> None:
    box_w, box_h, max_size, min_size = _box()
    fitted = fit_text(RU * 2, box_w, box_h, max_size, min_size)
    assert min_size <= fitted.size < max_size
    assert not fitted.truncated
    assert " ".join(fitted.lines) == RU * 2


def test_every_fitted_line_is_within_the_box_width_and_the_line_budget() -> None:
    box_w, box_h, max_size, min_size = _box()
    for text in (EN, RU, RU * 2, "слово " * 18, "Supercalifragilisticexpialidocious " * 3):
        fitted = fit_text(text, box_w, box_h, max_size, min_size)
        font = card_render._font(fitted.size)
        assert 1 <= len(fitted.lines) <= MAX_LINES
        stroke = card_render._stroke_px(fitted.size)
        assert all(font.getlength(line) <= box_w - 2 * stroke for line in fitted.lines)
        assert card_render._block_height(font, len(fitted.lines)) <= box_h


def test_overflowing_text_is_cut_with_an_ellipsis_and_still_fits() -> None:
    box_w, box_h, max_size, min_size = _box()
    fitted = fit_text("очень длинное пожелание " * 30, box_w, box_h, max_size, min_size)
    assert fitted.truncated
    assert fitted.size == min_size
    assert fitted.lines[-1].endswith(ELLIPSIS)
    assert len(fitted.lines) <= MAX_LINES


def test_a_single_word_wider_than_the_box_is_broken_by_characters() -> None:
    box_w, box_h, max_size, min_size = _box()
    fitted = fit_text("Ж" * 30, box_w, box_h, max_size, min_size)
    font = card_render._font(fitted.size)
    assert not fitted.truncated
    assert len(fitted.lines) > 1
    assert "".join(fitted.lines) == "Ж" * 30
    assert all(font.getlength(line) <= box_w for line in fitted.lines)


def test_an_endless_single_word_keeps_what_fits_plus_an_ellipsis() -> None:
    box_w, box_h, max_size, min_size = _box()
    fitted = fit_text("Ж" * 400, box_w, box_h, max_size, min_size)
    font = card_render._font(fitted.size)
    assert fitted.truncated
    assert fitted.lines != [ELLIPSIS]  # still shows text, not a bare ellipsis
    assert fitted.lines[-1].endswith(ELLIPSIS)
    assert len(fitted.lines) <= MAX_LINES
    assert all(font.getlength(line) <= box_w for line in fitted.lines)


def test_overflow_renders_instead_of_raising() -> None:
    out = _open(draw_short_text(_png((0, 0, 0)), "очень длинное пожелание " * 40))
    assert _bright_pixels(out, int(SIZE * 0.5), SIZE) > 0


def test_wrap_text_keeps_words_whole_when_they_fit() -> None:
    font = card_render._font(40)
    lines = wrap_text("one two three four five six", font, font.getlength("one two three"))
    assert lines[0] == "one two three"
    assert " ".join(lines) == "one two three four five six"


# ----- async entry point and fallback -----


@pytest.mark.asyncio
async def test_render_card_image_returns_the_phrase_version() -> None:
    original = _png()
    image, drawn = await render_card_image(original, EN)
    assert drawn is True
    assert image != original
    assert _open(image).size == (SIZE, SIZE)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", ["", "   ", None])
async def test_no_phrase_means_the_clean_original_comes_back(empty: str | None) -> None:
    original = _png()
    assert await render_card_image(original, empty) == (original, False)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_undecodable_image_falls_back_to_the_original(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    assert await render_card_image(b"not an image", EN) == (b"not an image", False)
    assert "rendering failed" in caplog.text


@pytest.mark.asyncio
async def test_missing_font_falls_back_to_the_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_render, "FONT_PATH", Path("does/not/exist.ttf"))
    original = _png()
    assert await render_card_image(original, EN) == (original, False)


@pytest.mark.asyncio
async def test_any_drawing_error_falls_back_to_the_original(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(original: bytes, text: str) -> bytes:
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(card_render, "draw_short_text", boom)
    original = _png()
    assert await render_card_image(original, EN) == (original, False)


@pytest.mark.asyncio
async def test_drawing_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def spy(original: bytes, text: str) -> bytes:
        seen.append(threading.get_ident())
        return b"drawn"

    monkeypatch.setattr(card_render, "draw_short_text", spy)
    assert await render_card_image(b"x", EN) == (b"drawn", True)
    assert seen and seen[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_a_slow_render_does_not_stall_other_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(original: bytes, text: str) -> bytes:
        time.sleep(0.4)
        return b"drawn"

    monkeypatch.setattr(card_render, "draw_short_text", slow)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        await render_card_image(b"x", EN)
    finally:
        task.cancel()
    # A blocked loop would have produced ~0 ticks; a free one gets dozens during 0.4 s.
    assert ticks >= 15
