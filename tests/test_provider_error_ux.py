"""Provider failures show stable localized text, never the raw provider error body."""
from __future__ import annotations

import logging
import re
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from handlers import main
from handlers.states import CardStates
from services.providers.openai_image import OpenAIImageError
from services.providers.openai_text import OpenAITextError
from services.proxi import ProxiAPIError
from services.storage import LastCardContext, get_storage
from services.yandex_gpt import YandexGPTError
from utils.i18n import t

# Special characters, a script tag, an unclosed tag and a stray closing tag.
HOSTILE = '<b>boom & <script>alert(1)</script> <a href="x">unclosed </i> 5 < 6 > 3 &nbsp'
LEAK_MARKERS = ("boom", "script", "alert", "unclosed", "nbsp")


def _assert_generic_telegram_safe(text: str, key: str, lang: str) -> None:
    assert text == t(key, lang)
    assert "<" not in text and ">" not in text
    assert not re.search(r"&(?!(?:amp|lt|gt|quot|#\d+);)", text)
    for marker in LEAK_MARKERS:
        assert marker not in text


def _sent_texts(*mocks: AsyncMock) -> list[str]:
    return [str(c.args[0]) for m in mocks for c in m.await_args_list if c.args]


# ----- Wizard generation path -----


WIZARD_ERRORS = [
    (ProxiAPIError, "err_image"),
    (OpenAIImageError, "err_image"),
    (YandexGPTError, "err_text"),
    (OpenAITextError, "err_text"),
    (RuntimeError, "err_generic"),
]


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize(("exc_type", "key"), WIZARD_ERRORS)
@pytest.mark.asyncio
async def test_wizard_provider_error_is_generic_and_logged(
    exc_type: type[Exception],
    key: str,
    lang: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    status_msg.delete = AsyncMock()
    anchor = MagicMock()
    anchor.answer = AsyncMock(return_value=status_msg)
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "occasion": "occasion_loved",
            "image_description": "cake",
            "holiday": "день рождения",
            "image_style": "style_realistic",
            "text_style": "text_warm",
        }
    )

    caplog.set_level(logging.ERROR)
    with (
        patch.object(main, "_generation_preflight_alert", AsyncMock(return_value=None)),
        patch.object(main, "run_card_generation", AsyncMock(side_effect=exc_type(HOSTILE))),
    ):
        await main._run_card_generation_from_wizard(MagicMock(), anchor, state, 1, lang)  # type: ignore[arg-type]

    status_msg.edit_text.assert_awaited_once()
    _assert_generic_telegram_safe(status_msg.edit_text.await_args.args[0], key, lang)

    # Nothing else the user sees carries the provider body either.
    for text in _sent_texts(anchor.answer, status_msg.edit_text):
        for marker in LEAK_MARKERS:
            assert marker not in text

    # Retry UX preserved: back on the signature step with its keyboard.
    assert state.set_state.await_args_list[-1] == call(CardStates.signature_toggle)
    assert anchor.answer.await_args_list[-1].args[0] == t("step6_signature_toggle", lang)
    assert anchor.answer.await_args_list[-1].kwargs["reply_markup"] is not None

    # Technical details are logged server-side.
    assert HOSTILE in caplog.text


# ----- Regeneration paths (share the same error strings) -----


def _regen_cq() -> MagicMock:
    cq = MagicMock()
    cq.from_user.id = 42
    cq.message = MagicMock()
    cq.message.photo = [MagicMock(file_id="photo123")]
    cq.answer = AsyncMock()
    cq.message.answer = AsyncMock()
    cq.message.answer_photo = AsyncMock()
    return cq


def _save_last_card() -> None:
    st = get_storage()
    st.set_user_lang(42, "ru")
    st.save_last_card(
        42,
        LastCardContext(
            occasion="occasion_loved",
            image_description="cake",
            holiday="день рождения",
            image_style="style_realistic",
            text_style="text_warm",
            lang="ru",
            image_prompt_en="cake",
            photo_file_id="photo123",
            caption_html="Привет",
        ),
    )


REGEN_CASES = [
    ("regen_text", "run_text_only", "text_provider_configured", YandexGPTError, "err_text"),
    ("regen_text", "run_text_only", "text_provider_configured", OpenAITextError, "err_text"),
    ("regen_card_lang", "run_text_only", "text_provider_configured", YandexGPTError, "err_text"),
    ("regen_image", "run_image_only", "image_provider_configured", ProxiAPIError, "err_image"),
    ("regen_image", "run_image_only", "image_provider_configured", OpenAIImageError, "err_image"),
]


@pytest.mark.parametrize(("handler", "run_fn", "configured_fn", "exc_type", "key"), REGEN_CASES)
@pytest.mark.asyncio
async def test_regen_provider_error_is_generic(
    handler: str,
    run_fn: str,
    configured_fn: str,
    exc_type: type[Exception],
    key: str,
) -> None:
    _save_last_card()
    cq = _regen_cq()

    with (
        patch.object(main, "can_consume_generation", return_value=True),
        patch.object(main, configured_fn, return_value=True),
        patch.object(main, run_fn, AsyncMock(side_effect=exc_type(HOSTILE))),
    ):
        await getattr(main, handler)(cq)

    cq.message.answer.assert_awaited_once()
    _assert_generic_telegram_safe(cq.message.answer.await_args.args[0], key, "ru")
    cq.message.answer_photo.assert_not_called()
