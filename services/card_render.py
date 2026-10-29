"""
Draws the card's short phrase onto the clean generated image with Pillow and the bundled PT Serif Bold
(SIL OFL 1.1, Cyrillic + Latin; see assets/fonts/).

The clean image is never modified: callers keep it so the phrase can be re-drawn later. All sizes are
fractions of the image, so any provider output size works. Drawing is CPU work, so the async entry point
runs it in a worker thread; every call builds its own Image and font objects, nothing is shared.
"""
from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "PTSerif-Bold.ttf"

MARGIN_X = 0.08  # share of the width kept clear left and right of the text
MARGIN_BOTTOM = 0.07  # share of the height between the text block and the bottom edge
MAX_BLOCK_HEIGHT = 0.36  # the text block never takes more than this share of the height
MAX_FONT = 0.085  # share of the width
MIN_FONT = 0.040
MIN_FONT_PX = 8
MAX_LINES = 5
LINE_SPACING = 1.25  # baseline-to-baseline distance in font sizes
STROKE = 0.04  # outline width in font sizes
SCRIM_ALPHA = 0.68  # darkness behind the text: white text stays above WCAG AAA contrast on a white image
ELLIPSIS = "…"

_WHITE = (255, 255, 255, 255)
_BLACK = (0, 0, 0, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    # BASIC layout: the same metrics everywhere (no dependency on libraqm being present).
    return ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)


def _stroke_px(size: int) -> int:
    return max(1, round(size * STROKE))


def _split_long_word(word: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    if font.getlength(word) <= max_width:
        return [word]
    pieces: list[str] = []
    piece = ""
    for ch in word:
        if piece and font.getlength(piece + ch) > max_width:
            pieces.append(piece)
            piece = ch
        else:
            piece += ch
    if piece:
        pieces.append(piece)
    return pieces


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float, *, exact: bool = False) -> list[str]:
    """Greedy word wrap, one paragraph per source line; a word wider than the box is split by characters."""
    lines: list[str] = []
    if exact:
        for paragraph in text.split("\n"):
            if not paragraph:
                lines.append("")
            while paragraph:
                end = 1
                while end < len(paragraph) and font.getlength(paragraph[:end + 1]) <= max_width:
                    end += 1
                if end < len(paragraph):
                    boundary = paragraph.rfind(" ", 0, end)
                    if boundary > 0:
                        end = boundary + 1
                lines.append(paragraph[:end])
                paragraph = paragraph[end:]
        return lines
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            for piece in _split_long_word(word, font, max_width):
                candidate = f"{current} {piece}" if current else piece
                if current and font.getlength(candidate) > max_width:
                    lines.append(current)
                    current = piece
                else:
                    current = candidate
        if current:
            lines.append(current)
    return lines


@dataclass(frozen=True)
class FittedText:
    lines: list[str]
    size: int
    truncated: bool


def _block_height(font: ImageFont.FreeTypeFont, line_count: int) -> int:
    ascent, descent = font.getmetrics()
    return ascent + (line_count - 1) * round(font.size * LINE_SPACING) + descent


def fit_text(
    text: str, box_width: int, box_height: int, max_size: int, min_size: int, *, exact: bool = False,
) -> FittedText:
    """
    Largest font size (``max_size`` down to ``min_size``) at which ``text`` wraps into at most MAX_LINES
    lines inside the box. If it does not fit even at ``min_size`` it is shortened word by word and ends
    with an ellipsis, so the result always fits.
    """

    def attempt(candidate: str, size: int) -> list[str] | None:
        font = _font(size)
        lines = wrap_text(candidate, font, box_width - 2 * _stroke_px(size), exact=exact)
        if lines and len(lines) <= MAX_LINES and _block_height(font, len(lines)) <= box_height:
            return lines
        return None

    for size in range(max_size, min_size - 1, -2):
        lines = attempt(text, size)
        if lines:
            return FittedText(lines, size, truncated=False)

    words = text.split()
    while len(words) > 1:
        words.pop()
        lines = attempt(" ".join(words).rstrip(" ,;:-—–") + ELLIPSIS, min_size)
        if lines:
            return FittedText(lines, min_size, truncated=True)
    # What is left is one word that does not fit by itself: keep as many of its characters as fit.
    word = words[0] if words else ""
    for end in range(len(word) - 1, 0, -1):
        lines = attempt(word[:end] + ELLIPSIS, min_size)
        if lines:
            return FittedText(lines, min_size, truncated=True)
    return FittedText([ELLIPSIS], min_size, truncated=True)


def _scrim(width: int, height: int, top: int, solid_top: int) -> Image.Image:
    """Black overlay: transparent above ``top``, easing in to SCRIM_ALPHA at ``solid_top``, solid below."""
    column = Image.new("L", (1, height), 0)
    pixels = []
    for y in range(height):
        if y >= solid_top:
            t = 1.0
        elif y <= top or solid_top <= top:
            t = 0.0
        else:
            t = (y - top) / (solid_top - top)
            t = t * t * (3 - 2 * t)
        pixels.append(round(255 * SCRIM_ALPHA * t))
    column.putdata(pixels)
    overlay = Image.new("RGBA", (width, height), _BLACK)
    overlay.putalpha(column.resize((width, height), Image.Resampling.NEAREST))
    return overlay


def draw_short_text(original: bytes, text: str, *, exact: bool = False) -> bytes:
    """Return a PNG of ``original`` with ``text`` centred near the bottom. Raises on undecodable input."""
    with Image.open(io.BytesIO(original)) as source:
        base = source.convert("RGBA")
    width, height = base.size

    box_width = round(width * (1 - 2 * MARGIN_X))
    box_height = round(height * MAX_BLOCK_HEIGHT)
    max_size = max(MIN_FONT_PX, round(width * MAX_FONT))
    min_size = max(MIN_FONT_PX, round(width * MIN_FONT))
    fitted = fit_text(text, box_width, box_height, max_size, min_size, exact=exact)
    if exact and fitted.truncated:
        # Actual output geometry can be wider/shorter than the nominal validation square. Reduce font
        # size rather than silently shortening an inscription the user fixed.
        fitted = fit_text(text, box_width, box_height, max_size, MIN_FONT_PX, exact=True)
        if fitted.truncated:
            raise ValueError("Exact inscription does not fit the actual image")

    font = _font(fitted.size)
    ascent, _ = font.getmetrics()
    pitch = round(fitted.size * LINE_SPACING)
    block_height = _block_height(font, len(fitted.lines))
    block_top = height - round(height * MARGIN_BOTTOM) - block_height

    pad = round(fitted.size * 0.9)
    solid_top = max(0, block_top - pad)
    ramp = max(round(height * 0.10), pad)
    composed = Image.alpha_composite(base, _scrim(width, height, max(0, solid_top - ramp), solid_top))

    draw = ImageDraw.Draw(composed)
    stroke = _stroke_px(fitted.size)
    for index, line in enumerate(fitted.lines):
        draw.text(
            (width / 2, block_top + ascent + index * pitch),
            line,
            font=font,
            fill=_WHITE,
            anchor="ms",
            stroke_width=stroke,
            stroke_fill=_BLACK,
        )

    out = io.BytesIO()
    composed.convert("RGB").save(out, format="PNG")
    return out.getvalue()


# --- exact (user-approved) inscriptions -------------------------------------------------------------------
#
# AI phrases are cleaned and, if need be, shortened (``fit_text`` ends them with an ellipsis). A phrase the
# user wrote or approved must be drawn exactly as given, so it is checked *before* generation: it either
# fits as-is or the user is asked to change it. Validation uses a nominal 1024 px square; the exact
# renderer also checks the actual output geometry and never uses a shortened fit.

INSCRIPTION_MAX_CHARS = 120
_CHECK_SIZE = 1024
_MISSING_GLYPH = "￿"  # no font maps it, so it renders the font's ".notdef" box


@dataclass(frozen=True)
class InscriptionCheck:
    ok: bool
    reason: str = ""
    """``empty`` / ``too_long`` / ``unsupported`` / ``does_not_fit`` when not ok."""
    detail: str = ""
    """The offending characters for ``unsupported``."""


def _unsupported_chars(text: str) -> str:
    font = _font(MIN_FONT_PX * 4)
    missing = font.getmask(_MISSING_GLYPH)
    reference = (bytes(missing), missing.size)
    bad: list[str] = []
    for ch in text:
        if ch.isspace() or ch in bad:
            continue
        glyph = font.getmask(ch)
        if (bytes(glyph), glyph.size) == reference:
            bad.append(ch)
    return "".join(bad)


def check_inscription(text: str) -> InscriptionCheck:
    """Whether ``text`` can be drawn on a card exactly as written (see the block comment above)."""
    if not (text or "").strip():
        return InscriptionCheck(False, "empty")
    if len(text) > INSCRIPTION_MAX_CHARS:
        return InscriptionCheck(False, "too_long")
    bad = _unsupported_chars(text)
    if bad:
        return InscriptionCheck(False, "unsupported", bad)
    fitted = fit_text(
        text,
        round(_CHECK_SIZE * (1 - 2 * MARGIN_X)),
        round(_CHECK_SIZE * MAX_BLOCK_HEIGHT),
        max(MIN_FONT_PX, round(_CHECK_SIZE * MAX_FONT)),
        max(MIN_FONT_PX, round(_CHECK_SIZE * MIN_FONT)),
        exact=True,
    )
    if fitted.truncated:
        return InscriptionCheck(False, "does_not_fit")
    return InscriptionCheck(True)


async def render_card_image(original: bytes, short_text: str, *, exact: bool = False) -> tuple[bytes, bool]:
    """
    ``(image to send, phrase_drawn)``. Never raises: with no phrase, or if drawing fails for any reason
    (bad font file, undecodable image, ...), the clean original comes back with ``phrase_drawn=False``.
    """
    text = (short_text or "").strip()
    if not text:
        return original, False
    try:
        if exact:
            return await asyncio.to_thread(draw_short_text, original, text, exact=True), True
        return await asyncio.to_thread(draw_short_text, original, text), True
    except Exception:
        logger.exception("card text rendering failed; sending the image without the embedded phrase")
        return original, False
