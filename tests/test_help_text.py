"""In-bot /help text matches the implemented wizard order and registered commands."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.bot_commands import setup_bot_commands
from utils.i18n import t

# One marker per numbered wizard step, in the order the wizard asks them:
# recipient -> holiday (+ optional details) -> image idea -> image style -> caption style
# -> optional greeting/address -> optional signature.
STEP_MARKERS = {
    "ru": ["близкие", "праздник", "идея картинки", "стиль картинки", "стиль текста", "обращение", "подпись"],
    "en": ["loved ones", "holiday", "image idea", "image style", "caption style", "greeting/address", "signature"],
}
DETAILS_MARKER = {"ru": "возраст", "en": "age"}
SUMMARY_MARKER = {"ru": "сводку", "en": "summary"}
NO_CONFIRM_MARKER = {"ru": "без отдельного подтверждения", "en": "no separate confirmation"}


def _numbered_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if re.match(r"^\d\) ", line)]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_lists_wizard_steps_in_implemented_order(lang: str) -> None:
    lines = _numbered_lines(t("help_text", lang))
    assert [line[:2] for line in lines] == [f"{i})" for i in range(1, 8)]
    for line, marker in zip(lines, STEP_MARKERS[lang], strict=True):
        assert marker in line.lower()


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_marks_optional_steps_and_occasion_details(lang: str) -> None:
    lines = _numbered_lines(t("help_text", lang))
    assert DETAILS_MARKER[lang] in lines[1].lower()
    optional = "по желанию" if lang == "ru" else "optional"
    assert optional in lines[5].lower()
    assert optional in lines[6].lower()


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_says_generation_starts_from_summary_without_confirmation(lang: str) -> None:
    text = t("help_text", lang)
    last_step = text.index(_numbered_lines(text)[-1])
    tail = text[last_step:]
    assert SUMMARY_MARKER[lang] in tail
    assert NO_CONFIRM_MARKER[lang] in tail


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["ru", "en"])
async def test_help_commands_match_registered_menu_commands(lang: str) -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()
    await setup_bot_commands(bot)
    registered = {c.command for c in bot.set_my_commands.await_args_list[0].args[0]}

    listed = set(re.findall(r"^/(\w+) ", t("help_text", lang), flags=re.MULTILINE))
    assert listed == registered == {"start", "cancel", "lang", "help"}


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.unbalanced = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack.pop() != tag:
            self.unbalanced = True


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_is_valid_telegram_html(lang: str) -> None:
    text = t("help_text", lang)
    parser = _TagCollector()
    parser.feed(text)
    assert not parser.stack and not parser.unbalanced
    assert re.sub(r"</?b>", "", text).count("<") == 0
    assert not re.search(r"&(?!(?:amp|lt|gt|quot|#\d+);)", text)
