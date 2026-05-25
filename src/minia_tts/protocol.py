"""Protocol constants, state, and helper functions for the TTS service."""

from __future__ import annotations

from enum import StrEnum

import asyncio
import json
import logging
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from minia_sockets.server import SOCKET_DISCONNECT_ERRORS
from minia_tts.cancellation import CancellationToken
from minia_tts.kokoro.constants import SAMPLE_RATE

logger = logging.getLogger(__name__)

# Command bytes
CMD_TEXT = 0x01
CMD_STOP = 0x02
CMD_STATUS = 0x03

# Response bytes
RES_READY = 0x10
RES_STATUS = 0x11
RES_AUDIO = 0x12
RES_ERROR = 0x13


# Text commands embedded in text payload
class TTSCommand(StrEnum):
    """Text-based sub-commands for the TTS protocol."""

    STOP = "/stop"
    STATUS = "/status"
    LIST_VOICES = "/list-voices"
    VOICE = "/voice"
    LANGUAGE = "/language"
    SPEED = "/speed"
    VOLUME = "/volume"

    @property
    def has_arg(self) -> bool:
        """Whether this command takes an argument after the prefix."""
        return self in (
            TTSCommand.VOICE,
            TTSCommand.LANGUAGE,
            TTSCommand.SPEED,
            TTSCommand.VOLUME,
        )

    @property
    def prefix(self) -> str:
        """The full prefix string to match against incoming text."""
        return f"{self.value} " if self.has_arg else self.value


def pack_audio_frame(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert audio to int16 and pack into protocol frame bytes."""
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    header = struct.pack("!HI", sample_rate, len(audio_int16))
    return header + audio_int16.tobytes()


@dataclass
class TTSConfig:
    """TTS configuration settings."""

    voice: str = "af_heart"
    language: str = "en"
    speed: float = 1.0
    volume: float = 1.0
    output_mode: str = "both"


@dataclass
class SynthesisState:
    """Runtime synthesis state."""

    speaking: bool = False
    current_text: str = ""
    _stop_handled: bool = False
    _cancellation: CancellationToken = field(
        default_factory=CancellationToken, repr=False
    )


@dataclass
class TTSState:
    """Mutable state shared between the socket handler and TTS provider."""

    provider: Any = None
    output_playback: Any = None
    output_stream: Any = None
    command_queue: asyncio.Queue | None = None
    config: TTSConfig = field(default_factory=TTSConfig)
    synthesis: SynthesisState = field(default_factory=SynthesisState)


def _encode_frame(writer, cmd: int, payload: bytes) -> None:
    """Encode and write a binary frame to the socket."""
    writer.write(struct.pack("!B", cmd))
    writer.write(struct.pack("!H", len(payload)))
    writer.write(payload)


async def _send_error(writer, message: str) -> None:
    """Send ERROR response."""
    payload = message[:1000].encode("utf-8")
    writer.write(struct.pack("!B", RES_ERROR))
    writer.write(struct.pack("!H", len(payload)))
    writer.write(payload)
    await writer.drain()


async def _send_ok(writer) -> None:
    """Send a simple OK response."""
    payload = json.dumps({"speaking": False}).encode("utf-8")
    writer.write(struct.pack("!B", RES_STATUS))
    writer.write(struct.pack("!H", len(payload)))
    writer.write(payload)
    await writer.drain()


async def _send_audio_frames(writer, audio_chunk: np.ndarray) -> int:
    """Convert audio chunk to int16 frames and send to socket.

    Returns the number of frames sent.
    """
    frame_count = 0
    MAX_SAMPLES = 20000
    for offset in range(0, len(audio_chunk), MAX_SAMPLES):
        chunk = audio_chunk[offset : offset + MAX_SAMPLES]
        frame = pack_audio_frame(chunk, SAMPLE_RATE)
        writer.write(struct.pack("!B", RES_AUDIO))
        writer.write(struct.pack("!H", len(frame)))
        writer.write(frame)
        try:
            await writer.drain()
        except SOCKET_DISCONNECT_ERRORS:
            break
        frame_count += 1
    return frame_count
