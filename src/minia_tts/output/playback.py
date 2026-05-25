"""Server-side audio playback via sounddevice (threaded, non-blocking).

The playback thread owns the sounddevice OutputStream and drains audio
chunks from a thread-safe queue.  All public methods on PlaybackOutput
return immediately without blocking the event loop.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any

import numpy as np

from minia_tts.output.base import AudioOutput

logger = logging.getLogger(__name__)

# Sentinel objects for the playback queue
_STOP = object()
_SHUTDOWN = object()


class _PlaybackThread(threading.Thread):
    """Background thread that writes audio to sounddevice.

    Runs until ``_SHUTDOWN`` is received.  Drains remaining audio on
    ``_STOP`` before exiting (if ``drain_on_stop`` is True).
    """

    def __init__(
        self,
        sample_rate: int,
        device_id: int | None,
        q: queue.Queue,
        logger: logging.Logger,
    ) -> None:
        super().__init__(daemon=True, name="minia-tts-playback")
        self._sample_rate = sample_rate
        self._device_id = device_id
        self._q = q
        self._log = logger
        self._stream: Any = None
        self._stopped = False

    # -- public helpers ------------------------------------------------

    def is_alive_and_stream_open(self) -> bool:
        return self.is_alive() and self._stream is not None

    def _reset_stopped(self) -> None:
        """Reset stopped flag for next synthesis (thread-safe)."""
        self._stopped = False

    # -- thread entry point --------------------------------------------

    def run(self) -> None:
        self._open_stream()
        if self._stream is not None:
            self._log.info(
                "[TTS] Playback thread started (samplerate=%d)", self._sample_rate
            )
        try:
            while True:
                item = self._q.get()
                if item is _STOP:
                    self._drain_and_stop()
                    self._stopped = True
                elif item is _SHUTDOWN:
                    self._stop_stream()
                    break
                else:
                    self._write_chunk(item)
        except Exception:
            if self._stream is None:
                self._log.info("Playback thread exiting (stream closed)")
            else:
                self._log.exception("Playback thread crashed")
        finally:
            self._stop_stream()
            self._log.info("[TTS] Playback thread stopped")

    # -- internal ------------------------------------------------------

    def _open_stream(self) -> None:
        import sounddevice as sd  # type: ignore[import-untyped]

        kwargs: dict = {
            "blocksize": 1024,
            "latency": "low",
        }
        if self._device_id is not None:
            kwargs["device"] = self._device_id

        try:
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype=np.float32,
                **kwargs,
            )
            self._stream.start()
        except Exception:
            self._log.exception("Failed to open sounddevice stream")
            self._stream = None

    def _write_chunk(self, item: tuple[np.ndarray, int]) -> None:
        audio, sr = item
        if audio is None or len(audio) == 0:
            return

        # Ensure mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # Resample if needed
        if sr != self._sample_rate:
            orig_duration = len(audio) / sr
            target_len = int(orig_duration * self._sample_rate)
            orig_t = np.linspace(0.0, 1.0, len(audio))
            new_t = np.linspace(0.0, 1.0, target_len)
            audio = np.interp(new_t, orig_t, audio)

        if self._stream is None:
            return

        for i in range(0, len(audio), 4096):
            if self._stopped:
                break
            chunk = audio[i : i + 4096]
            try:
                self._stream.write(chunk)
            except Exception:
                raise

    def _drain_and_stop(self) -> None:
        """Write remaining items then stop."""
        self._stopped = True
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is _STOP or item is _SHUTDOWN:
                continue
            self._write_chunk(item)

    def _stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class PlaybackOutput(AudioOutput):
    """Plays audio through the system speakers using sounddevice.

    All public methods are non-blocking.  Audio is forwarded to a
    background thread via a thread-safe queue.
    """

    def __init__(self, sample_rate: int = 24000, device_id: int | None = None) -> None:
        self._sample_rate = sample_rate
        self._device_id = device_id
        self._q: queue.Queue = queue.Queue(maxsize=512)
        self._thread: _PlaybackThread | None = None
        self._lock = threading.Lock()
        self._shutdown_requested = False

    # -- lifecycle -----------------------------------------------------

    def _ensure_thread(self) -> None:
        """Start the playback thread lazily (reentrant-safe)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive_and_stream_open():
                return
            if self._shutdown_requested:
                return
            t = _PlaybackThread(
                sample_rate=self._sample_rate,
                device_id=self._device_id,
                q=self._q,
                logger=logger,
            )
            t.start()
            self._thread = t

    # -- AudioOutput interface -----------------------------------------

    async def play(self, audio: np.ndarray, sample_rate: int) -> None:
        """Queue audio for playback.  Returns immediately."""
        if len(audio) == 0 or self._shutdown_requested:
            return
        self._ensure_thread()
        try:
            self._q.put_nowait((audio, sample_rate))
        except queue.Full:
            logger.warning("Playback queue full, dropping audio chunk")
        logger.debug("[TTS] Queued audio chunk (%d samples)", len(audio))

    async def stop(self) -> None:
        """Signal the playback thread to stop after draining."""
        self._drain_queue()
        try:
            self._q.put_nowait(_STOP)
        except Exception:
            pass

    def _drain_queue(self) -> None:
        """Drain all items from the queue (called from event loop)."""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def is_playing(self) -> bool:
        if self._thread is None:
            return False
        return self._thread.is_alive_and_stream_open()

    def reset_stopped(self) -> None:
        """Reset the playback thread's stopped flag for next TEXT."""
        if self._thread is not None:
            self._thread._reset_stopped()

    def wait_for_ready(self) -> None:
        """Block until the playback thread has opened and started the stream."""
        self._ensure_thread()
        import time

        thread = self._thread
        if thread is None:
            return
        start = time.monotonic()
        while not thread.is_alive_and_stream_open():
            if time.monotonic() - start > 5.0:
                logger.warning("[TTS] Playback stream did not open within 5s")
                return
            time.sleep(0.05)

    def shutdown(self) -> None:
        """Stop and release the playback thread."""
        with self._lock:
            self._shutdown_requested = True
        try:
            self._q.put_nowait(_SHUTDOWN)
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
