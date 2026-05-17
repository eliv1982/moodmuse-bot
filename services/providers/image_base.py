"""
Image generation provider protocol.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ImageProvider(Protocol):
    """Shared interface for greeting-card image generation."""

    async def generate_image(self, prompt: str) -> bytes:
        """Generate image bytes from an English prompt."""
        ...
