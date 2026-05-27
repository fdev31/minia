"""minia_tts — Text-to-speech service with Kokoro."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from minia_tts.server import main

__all__ = ["main"]


def __getattr__(name: str):
    if name == "main":
        from minia_tts.server import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
