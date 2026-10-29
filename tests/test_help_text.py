"""In-bot /help text matches the implemented creation flow and registered commands."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.bot_commands import setup_bot_commands
from utils.i18n import t

MODE_MARKERS = {
    "ru": ["выбрать из вариантов", "опишу своими словами"],
    "en": ["choose from options", "describe it in your own words"],
}
INSCRIPTION_MARKERS = {
    "ru": ["точный текст", "только после вашего одобрения", "без надписи"],
    "en": ["exact text", "only after you approve", "or none"],
}
CONFIRM_MARKER = {"ru": "только после кнопки «создать»", "en": "only after you press “create”"}


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_describes_both_creation_modes(lang: str) -> None:
    text = t("help_text", lang).lower()
    for marker in MODE_MARKERS[lang]:
        assert marker in text


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_explains_the_three_inscription_choices_and_that_ai_text_needs_approval(lang: str) -> None:
    text = t("help_text", lang).lower()
    for marker in INSCRIPTION_MARKERS[lang]:
        assert marker in text


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_says_the_image_is_created_only_after_confirmation(lang: str) -> None:
    text = t("help_text", lang).lower()
    assert CONFIRM_MARKER[lang] in text
    assert "without a separate confirmation" not in text and "без отдельного подтверждения" not in text


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
