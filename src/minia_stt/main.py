"""minia_stt — Speech-to-text client for minia.

Records audio from the microphone, transcribes it with Whisper,
and sends recognized text to the minia command socket.

Usage:
    minia-stt
"""

from __future__ import annotations

import asyncio
import logging
import sys

from minia_config import config
from minia_stt.audio_recorder import AudioRecorder
from minia_stt.client import STTClient
from minia_stt.transcriber import Transcriber

logger = logging.getLogger(__name__)


class SpeechListener:
    """Record mic → transcribe → send to minia."""

    def __init__(
        self,
        cmd_socket_path: str,
        model: str = "small",
        device: str = "auto",
        language: str | None = None,
        silence_threshold: float = 0.01,
        silence_duration: float = 2.0,
    ) -> None:
        self._cmd_socket_path = cmd_socket_path
        self._model = model
        self._device = device
        self._language = language
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration

    async def run(self) -> None:
        """Main listen loop."""
        logger.info("[STT] Starting speech listener")
        logger.info("[STT] Command socket: %s", self._cmd_socket_path)

        recorder = AudioRecorder(
            silence_threshold=self._silence_threshold,
            silence_duration=self._silence_duration,
        )
        transcriber = Transcriber(
            model=self._model,
            device=self._device,
            language=self._language,
        )

        async for audio_chunk in recorder.record():
            text = await transcriber.transcribe(audio_chunk)
            if text.strip():
                logger.info("[STT] Sending: '%s'", text[:100])
                async with STTClient(self._cmd_socket_path) as client:
                    await client.send_text(text.strip())


async def _main() -> None:
    cmd_socket_path = config.default.cmd_socket_path
    stt_config = config.stt

    listener = SpeechListener(
        cmd_socket_path=cmd_socket_path,
        model=getattr(stt_config, "model", "small"),
        device=getattr(stt_config, "device", "auto"),
        language=getattr(stt_config, "language", None),
        silence_threshold=getattr(stt_config, "silence_threshold", 0.01),
        silence_duration=getattr(stt_config, "silence_duration", 2.0),
    )
    await listener.run()


def main() -> None:
    """Entry point for minia-stt."""
    from minia_utils.logging import configure_logging, resolve_log_level

    configure_logging(
        log_level=resolve_log_level(config, "stt"),
        add_console=True,
    )
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
