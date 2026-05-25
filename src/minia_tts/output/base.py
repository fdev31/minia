"""Abstract base class for audio output backends."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


class AudioOutput(ABC):
    """Interface for audio output backends."""

    @abstractmethod
    async def play(self, audio: np.ndarray, sample_rate: int) -> None:
        """Play audio through this backend.

        Args:
            audio: float32 numpy array of audio samples.
            sample_rate: Sample rate in Hz.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop playback immediately."""

    @abstractmethod
    def is_playing(self) -> bool:
        """True if currently playing audio."""

    def shutdown(self) -> None:
        """Release resources."""

    async def __aenter__(self) -> "AudioOutput":
        return self

    async def __aexit__(self, *args: object) -> None:
        self.shutdown()
