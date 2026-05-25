"""Audio recording with energy-based voice activity detection."""

from __future__ import annotations

import asyncio
import logging
import queue

import numpy as np

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Records audio from microphone, detects speech boundaries.

    Uses energy-based VAD: when audio energy rises above threshold,
    speech is considered to have started. When it stays below threshold
    for SILENCE_DURATION, speech is considered to have ended.

    Yields np.ndarray chunks when speech ends.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        silence_threshold: float = 0.01,
        silence_duration: float = 2.0,
        duration: float = 0.5,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration
        self._duration = duration
        self._buffer_size = int(duration * sample_rate)
        self._speech_audio: list[np.ndarray] = []
        self._is_speaking = False
        self._silence_start: float | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=3)
        self._running = False
        self._thread: asyncio.Task | None = None

    async def record(self):
        """Async generator that yields speech chunks."""
        import sounddevice as sd  # type: ignore[import-untyped]

        self._running = True

        def _capture() -> None:
            try:
                with sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    blocksize=self._buffer_size,
                    dtype=np.float32,
                ) as stream:
                    while self._running:
                        try:
                            data, status = stream.read(self._buffer_size)
                            if status:
                                logger.debug("Audio status: %s", status)
                            self._process_chunk(data[:, 0] if data.ndim > 1 else data)
                            if not self._running:
                                break  # type: ignore[unreachable]
                        except Exception:
                            if self._running:
                                raise
            except Exception as e:
                if self._running:
                    logger.error("Audio capture error: %s", e)
                self._queue.put(None)

        self._thread = asyncio.create_task(asyncio.to_thread(_capture))

        while self._running:
            chunk = await asyncio.get_event_loop().run_in_executor(
                None, self._queue.get
            )
            if chunk is None:
                break
            yield chunk

        self._running = False
        if self._thread:
            try:
                await asyncio.wait_for(self._thread, timeout=2.0)
            except asyncio.TimeoutError:
                self._thread.cancel()

    def _process_chunk(self, data: np.ndarray) -> None:
        energy = np.mean(np.abs(data))

        if energy > self._silence_threshold:
            if not self._is_speaking:
                logger.debug("Speech detected")
                self._is_speaking = True
                self._silence_start = None
                if self._speech_audio:
                    self._speech_audio = []
            self._speech_audio.append(data.copy())
        else:
            if self._is_speaking:
                self._speech_audio.append(data.copy())
                if self._silence_start is None:
                    self._silence_start = asyncio.get_event_loop().time()
                elif (
                    asyncio.get_event_loop().time() - self._silence_start
                ) >= self._silence_duration:
                    self._is_speaking = False
                    self._silence_start = None
                    try:
                        self._queue.put_nowait(np.concatenate(self._speech_audio))
                    except queue.Full:
                        pass
                    self._speech_audio.clear()
