"""
Text generation provider protocol for caption and image-prompt refinement.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from utils.i18n import Lang


@runtime_checkable
class TextProvider(Protocol):
    """Shared interface for greeting text and image-prompt refinement."""

    async def generate_greeting_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float,
        max_tokens: int = 400,
        temperature: float = 0.65,
    ) -> str:
        """Generate greeting caption text."""
        ...

    async def enhance_image_prompt(
        self,
        *,
        draft_english_prompt: str,
        lang: Lang,
        timeout: float,
    ) -> str:
        """Refine English image prompt for diffusion models."""
        ...
