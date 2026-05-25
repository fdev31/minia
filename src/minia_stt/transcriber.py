"""Whisper transcription."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio chunks using Whisper."""

    def __init__(
        self,
        model: str = "small",
        device: str = "auto",
        language: str | None = None,
    ) -> None:
        self._model_name = model
        self._device = device
        self._language = language
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            import whisper  # type: ignore[import-not-found]

            device = self._device
            if device == "auto":
                import torch  # type: ignore[import-not-found]

                if torch.cuda.is_available():
                    device = "cuda"
                elif (
                    hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                ):
                    device = "mps"
                else:
                    device = "cpu"

            logger.info("Loading Whisper model '%s' on %s", self._model_name, device)
            self._model = whisper.load_model(self._model_name, device=device)
        return self._model

    async def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio and return text. Returns empty string for silence."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(audio, fp16=True, language=self._language),
        )
        text = str(result.get("text", "")).strip()
        if text:
            logger.debug("[STT] Transcribed: '%s'", text[:100])
        return text
