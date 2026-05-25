"""Text relay: sends LLM text chunks to TTS for synthesis and playback."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from minia_protocol import tts_synthesize, tts_stop
from minia_sockets.server import open_unix
from minia_tts.kokoro.constants import split_text

logger = logging.getLogger(__name__)


class TTSSpeaker:
    """Relay text from the event socket to the TTS server.

    Splits incoming text into sentences and sends them sequentially
    to the TTS command socket for synthesis. The TTS server handles
    all audio playback locally.
    """

    def __init__(self, cmd_socket_path: str) -> None:
        self._cmd_socket_path = cmd_socket_path
        self._cmd_sender: _CommandSender | None = None
        self._sentence_queue: asyncio.Queue[tuple[float, list[str]]] | None = None
        self._runner_task: asyncio.Task[None] | None = None
        self._stopped: bool = False

    async def __aenter__(self) -> TTSSpeaker:
        self._cmd_sender = _CommandSender(self._cmd_socket_path)
        logger.info("[Audio] Connected to TTS command socket")
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
            try:
                await self._runner_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run_queue(self) -> None:
        """Background task that drains the sentence queue in batches.

        Collects all queued batches and sends them as a single synthesis
        request, preventing the TTS server from interrupting itself.
        """
        assert self._sentence_queue is not None
        assert self._cmd_sender is not None
        while True:
            batch_sentences: list[str] = []
            # Collect all currently queued batches
            while True:
                try:
                    _ts, sentences = self._sentence_queue.get_nowait()
                    batch_sentences.extend(sentences)
                except asyncio.QueueEmpty:
                    break
            if not batch_sentences:
                await asyncio.sleep(0.2)
                continue
            combined = " ".join(s.strip() for s in batch_sentences if s.strip())
            if combined:
                logger.info("[Audio] Sending %d sentences to TTS", len(batch_sentences))
                await self._cmd_sender.send_text(combined)
            # Small delay to let any pending speak() calls add their batches
            # before the next collection cycle
            await asyncio.sleep(0.3)

    async def speak(self, text: str) -> None:
        """Send text to TTS for speaking (fire-and-forget)."""
        if self._stopped:
            return

        sentences = split_text(text)
        clean_sentences = [s.strip() for s in sentences if s.strip()]
        if not clean_sentences:
            return

        if self._runner_task is None or self._runner_task.done():
            self._sentence_queue = asyncio.Queue()
            self._runner_task = asyncio.create_task(self._run_queue())

        assert self._sentence_queue is not None
        await self._sentence_queue.put((time.monotonic(), clean_sentences))

    async def stop(self) -> None:
        """Stop TTS playback."""
        self._stopped = True
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
            try:
                await self._runner_task
            except (asyncio.CancelledError, Exception):
                pass
            self._runner_task = None
        if self._sentence_queue is not None:
            while not self._sentence_queue.empty():
                try:
                    self._sentence_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._sentence_queue = None
        if self._cmd_sender:
            await self._cmd_sender.send_stop()

    async def reset(self) -> None:
        """Reset after stop - allow new speak() calls."""
        self._stopped = False
        self._runner_task = None
        self._sentence_queue = None


class _CommandSender:
    """Fire-and-forget sender for TTS command socket."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path

    async def send_text(self, text: str) -> None:
        """Send text to synthesize."""
        async with open_unix(self._socket_path) as (reader, writer):
            writer.write((json.dumps(tts_synthesize(text)) + "\n").encode())
            await writer.drain()

    async def send_stop(self) -> None:
        """Send stop command."""
        async with open_unix(self._socket_path) as (reader, writer):
            writer.write((json.dumps(tts_stop()) + "\n").encode())
            await writer.drain()
