"""Minia audio listener — speaks LLM responses via TTS.

A standalone process that connects to the minia event socket,
reads all messages, and sends text chunks to TTS immediately.

Usage:
    minia-chatloop
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Callable

from minia_config import config
from minia_chatloop.client import run_event_client
from minia_chatloop.speaker import TTSSpeaker
from minia_protocol import EventType

logger = logging.getLogger(__name__)


class AudioListener:
    """Listen to minia event socket and relay text to TTS.

    Accumulates LLM streaming tokens in a buffer and flushes them
    at sentence boundaries or when the final response arrives.
    """

    def __init__(self, event_socket_path: str, tts_cmd_path: str) -> None:
        self._event_socket_path = event_socket_path
        self._tts_cmd_path = tts_cmd_path
        self._llm_buffer: str = ""
        self._waiting_for_final: bool = False
        self._flush_task: asyncio.Task | None = None
        self._tts: TTSSpeaker | None = None
        self._handlers: dict[str, Callable[[dict], Any]] = {}

    def _make_handlers(self, tts: TTSSpeaker) -> None:
        """Register message handlers."""

        def on_ready(msg: dict) -> None:
            logger.info("[Audio] Connected to minia server")

        def on_user_input(msg: dict) -> None:
            logger.info("[Audio] User: %s", msg.get("content", "")[:200])
            asyncio.create_task(tts.stop())
            asyncio.create_task(tts.reset())
            self._llm_buffer = ""
            self._waiting_for_final = False

        def on_text(msg: dict) -> None:
            chunk = msg.get("content", "")
            self._llm_buffer += chunk
            logger.info("[Audio] LLM text chunk: '%s'", chunk[:100])
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()
            self._flush_task = asyncio.create_task(
                self._flush_buffer(tts, threshold=100)
            )

        def on_final(msg: dict) -> None:
            full_response = msg.get("content", "")
            logger.info("[Audio] Final response: '%s'", full_response[:200])
            self._llm_buffer = ""
            self._waiting_for_final = True
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()
            asyncio.create_task(self._flush_buffer(tts, saved_content=full_response))

        def on_thinking(msg: dict) -> None:
            logger.info("[Audio] Thinking: %s", msg.get("content", "")[:200])

        def on_tool_call_start(msg: dict) -> None:
            logger.info("[Audio] Tool start: %s", msg.get("content", "")[:100])

        def on_tool_call(msg: dict) -> None:
            logger.info("[Audio] Tool result: %s", msg.get("content", "")[:200])

        def on_error(msg: dict) -> None:
            logger.info("[Audio] Error: %s", msg.get("content", "")[:200])

        def on_disconnected(msg: dict) -> None:
            logger.info("[Audio] Another client disconnected")

        def on_cleared(msg: dict) -> None:
            logger.info("[Audio] History cleared, resetting buffer")
            asyncio.create_task(tts.stop())
            asyncio.create_task(tts.reset())
            self._llm_buffer = ""
            self._waiting_for_final = False

        def on_compaction(msg: dict) -> None:
            content = msg.get("content", "")
            logger.info("[Audio] Compaction summary: '%s'", content[:200])
            asyncio.create_task(tts.speak(content))

        def on_usage(msg: dict) -> None:
            tokens = msg.get("tokens", "?")
            logger.info("[Audio] Token usage: %s", tokens)

        def on_tts_stop(msg: dict) -> None:
            asyncio.create_task(tts.stop())
            asyncio.create_task(tts.reset())

        self._handlers = {
            EventType.READY.value: on_ready,
            EventType.USER_INPUT.value: on_user_input,
            EventType.TEXT.value: on_text,
            EventType.FINAL.value: on_final,
            EventType.THINKING.value: on_thinking,
            EventType.TOOL_CALL_START.value: on_tool_call_start,
            EventType.TOOL_CALL.value: on_tool_call,
            EventType.ERROR.value: on_error,
            EventType.DISCONNECTED.value: on_disconnected,
            EventType.CLEARED.value: on_cleared,
            EventType.COMPACTION.value: on_compaction,
            EventType.USAGE.value: on_usage,
            EventType.TTS_STOP.value: on_tts_stop,
        }

    def _dispatch(self, msg: dict) -> None:
        """Dispatch a message to the appropriate handler."""
        handler = self._handlers.get(msg.get("type", ""))
        if handler:
            handler(msg)

    async def _flush_buffer(
        self, tts: TTSSpeaker, threshold: int = 0, saved_content: str = ""
    ) -> None:
        """Flush accumulated text to TTS.

        Flushes when a sentence boundary is found, when the buffer
        exceeds *threshold* characters, or when *saved_content* is
        provided (used by on_final to pass the full response).
        """
        await asyncio.sleep(0.5)
        text = saved_content if saved_content else self._llm_buffer
        if not text:
            return

        # Check for sentence boundary
        for sep in (". ", "! ", "? ", "\n", ".\n", "!\n", "?\n"):
            idx = text.rfind(sep)
            if idx > 0:
                to_speak = text[: idx + len(sep)]
                self._llm_buffer = text[idx + len(sep) :]
                logger.info(
                    "[Audio] Flushing buffer (%d chars): '%s'",
                    len(to_speak),
                    to_speak[:80],
                )
                await tts.speak(to_speak)
                return

        # No sentence boundary found, flush if buffer is large enough
        if len(text) >= threshold:
            self._llm_buffer = ""
            logger.info(
                "[Audio] Flushing buffer (%d chars): '%s'",
                len(text),
                text[:80],
            )
            await tts.speak(text)

    async def run(self) -> None:
        """Main listen loop."""
        logger.info("[Audio] Starting audio listener")
        logger.info("[Audio] Event socket: %s", self._event_socket_path)
        logger.info("[Audio] TTS cmd socket: %s", self._tts_cmd_path)

        async with TTSSpeaker(self._tts_cmd_path) as tts:
            self._tts = tts
            logger.info("[Audio] Connected to TTS and minia servers")
            self._make_handlers(tts)
            await run_event_client(
                self._event_socket_path,
                self._dispatch,
                auto_reconnect=True,
            )

        logger.info("[Audio] Listener stopped")


async def _main() -> None:
    event_socket_path = config.default.event_socket_path
    tts_cmd_path = config.tts.cmd_socket_path

    listener = AudioListener(event_socket_path, tts_cmd_path)
    await listener.run()


def main() -> None:
    """Entry point for minia-chatloop."""
    from minia_utils.logging import configure_logging, resolve_log_level

    configure_logging(
        log_level=resolve_log_level(config, "audio"),
        add_console=True,
    )
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
