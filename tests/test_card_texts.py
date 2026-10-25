"""Short phrase + expanded caption from one model reply (offline)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.card_generation import (
    CARD_TEXTS_MAX_TOKENS,
    CardTexts,
    card_texts_from_reply,
    run_card_generation,
    run_text_only,
)
from utils.card_texts import SHORT_TEXT_MAX_CHARS, clean_short_text, parse_card_texts
from utils.prompts import build_card_texts_user_prompt


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "TEXT_PROVIDER": "openai",
        "IMAGE_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


# ----- parse_card_texts -----


def test_parses_json_with_both_fields() -> None:
    raw = json.dumps({"short": "С днём рождения!", "full": "Пусть день будет светлым."}, ensure_ascii=False)
    assert parse_card_texts(raw) == ("С днём рождения!", "Пусть день будет светлым.")


def test_parses_json_inside_code_fence_and_prose() -> None:
    raw = '```json\n{"short": "Hello", "full": "Hello there, friend."}\n```'
    assert parse_card_texts(raw) == ("Hello", "Hello there, friend.")
    assert parse_card_texts('Sure! {"short": "Hi", "full": "Hi all."} Enjoy.') == ("Hi", "Hi all.")


def test_raw_newlines_inside_json_strings_are_accepted() -> None:
    raw = '{"short": "Roses are red", "full": "Roses are red,\nViolets are blue."}'
    assert parse_card_texts(raw) == ("Roses are red", "Roses are red,\nViolets are blue.")


def test_escaped_newlines_become_line_breaks_in_poetry() -> None:
    raw = r'{"short": "Строка", "full": "Строка первая,\nстрока вторая."}'
    assert parse_card_texts(raw)[1] == "Строка первая,\nстрока вторая."


def test_plain_text_reply_is_the_caption_with_no_short_phrase() -> None:
    assert parse_card_texts("Just a normal greeting.") == ("", "Just a normal greeting.")


def test_missing_full_reuses_short_so_the_caption_is_never_empty() -> None:
    assert parse_card_texts('{"short": "Only this"}') == ("Only this", "Only this")


def test_truncated_json_is_salvaged_instead_of_leaking_braces() -> None:
    raw = '{"short": "Be happy", "full": "Be happy today and every day, with all the people who'
    short, full = parse_card_texts(raw)
    assert short == "Be happy"
    assert full.startswith("Be happy today and every day")
    assert "{" not in full and '"full"' not in full


def test_empty_and_whitespace_replies_do_not_crash() -> None:
    assert parse_card_texts("") == ("", "")
    assert parse_card_texts("   ") == ("", "")


def test_non_string_fields_are_ignored() -> None:
    assert parse_card_texts('{"short": 5, "full": ["a"]}')[0] == ""


# ----- clean_short_text -----


def test_clean_short_text_keeps_cyrillic_and_latin_punctuation() -> None:
    assert clean_short_text("С днём рождения, Анна!") == "С днём рождения, Анна!"
    assert clean_short_text("Happy birthday — enjoy it…") == "Happy birthday — enjoy it…"


def test_clean_short_text_strips_quotes_emoji_and_control_characters() -> None:
    assert clean_short_text("«Счастья вам!» 🎉🎂") == "Счастья вам!"
    assert clean_short_text('"Stay golden" ❤️') == "Stay golden"
    assert clean_short_text("A‍B\x00C") == "ABC"


def test_clean_short_text_collapses_whitespace_to_one_line() -> None:
    assert clean_short_text("  Line one \n\n line   two\t") == "Line one line two"


def test_clean_short_text_caps_length_at_a_word_boundary() -> None:
    out = clean_short_text("слово " * 60)
    assert len(out) <= SHORT_TEXT_MAX_CHARS
    assert out.endswith("…")
    assert out[:-1].split()[-1] == "слово"


def test_clean_short_text_of_nothing_is_empty() -> None:
    assert clean_short_text("") == ""
    assert clean_short_text("🎉🎉") == ""


# ----- card_texts_from_reply -----


def test_caption_is_html_escaped_but_short_phrase_stays_plain() -> None:
    raw = json.dumps({"short": "Tom & Jerry <3", "full": "Tom & Jerry <3 forever"})
    texts = card_texts_from_reply(raw, 1024)
    assert texts.short_text == "Tom & Jerry <3"
    assert texts.caption_html == "Tom &amp; Jerry &lt;3 forever"


def test_caption_is_capped_to_the_telegram_limit() -> None:
    raw = json.dumps({"short": "Hi", "full": "x" * 5000})
    texts = card_texts_from_reply(raw, 100)
    assert len(texts.caption_html) == 100
    assert texts.caption_html.endswith("…")


def test_legacy_plain_reply_keeps_the_previous_caption_behaviour() -> None:
    texts = card_texts_from_reply("Plain <b>text</b>", 1024)
    assert texts == CardTexts(caption_html="Plain &lt;b&gt;text&lt;/b&gt;", short_text="")


# ----- prompt -----


@pytest.mark.parametrize(("lang", "marker"), [("en", "only in English"), ("ru", "только на русском")])
def test_user_prompt_asks_for_json_with_both_fields_in_the_card_language(lang: str, marker: str) -> None:
    prompt = build_card_texts_user_prompt("birthday", lang)  # type: ignore[arg-type]
    assert '"short"' in prompt and '"full"' in prompt
    assert "JSON" in prompt
    assert "birthday" in prompt
    assert marker in prompt


# ----- one request for both texts -----


def _text_provider(reply: str) -> MagicMock:
    provider = MagicMock()
    provider.generate_greeting_text = AsyncMock(return_value=reply)
    provider.enhance_image_prompt = AsyncMock(return_value="refined prompt")
    return provider


@pytest.mark.asyncio
async def test_run_text_only_uses_a_single_text_request_for_both_texts() -> None:
    provider = _text_provider(json.dumps({"short": "Be bright", "full": "Be bright and bold."}))
    with patch("services.card_generation.get_text_provider", return_value=provider):
        texts = await run_text_only(
            _settings(), occasion="occasion_loved", holiday="birthday", text_style="text_warm", lang="en"
        )

    provider.generate_greeting_text.assert_awaited_once()
    provider.enhance_image_prompt.assert_not_called()
    kwargs = provider.generate_greeting_text.await_args.kwargs
    assert kwargs["max_tokens"] == CARD_TEXTS_MAX_TOKENS
    assert texts == CardTexts(caption_html="Be bright and bold.", short_text="Be bright")


@pytest.mark.asyncio
async def test_run_card_generation_adds_no_extra_text_request_for_the_short_phrase() -> None:
    provider = _text_provider(json.dumps({"short": "Радости вам", "full": "Радости вам и тепла."}, ensure_ascii=False))
    image_provider = MagicMock()
    image_provider.generate_image = AsyncMock(return_value=b"CLEAN-IMAGE")

    with (
        patch("services.card_generation.get_text_provider", return_value=provider),
        patch("services.card_generation.get_image_provider", return_value=image_provider),
    ):
        card = await run_card_generation(
            _settings(),
            occasion="occasion_loved",
            image_description="mountains",
            holiday="день рождения",
            image_style="style_realistic",
            text_style="text_warm",
            lang="ru",
            image_prompt_override="a draft prompt",
        )

    # One refine call for the image prompt (pre-existing) and exactly one call for the card texts.
    provider.enhance_image_prompt.assert_awaited_once()
    provider.generate_greeting_text.assert_awaited_once()
    image_provider.generate_image.assert_awaited_once_with("refined prompt")
    assert card.image_bytes == b"CLEAN-IMAGE"
    assert card.texts == CardTexts(caption_html="Радости вам и тепла.", short_text="Радости вам")
    assert card.image_prompt_en == "refined prompt"
