"""TTS command socket types and audio frame constants.

The TTS command socket accepts commands from clients to the TTS server.
The TTS audio socket streams raw PCM frames to clients.

Usage
-----
Commands::

    from minia_protocol import tts_synthesize, tts_stop, tts_settings

    await writer.send(tts_synthesize("Hello"))
    await writer.send(tts_stop())
    await writer.send(tts_settings("voice", "af_bella"))

Audio frame layout::

    [num_samples: 4 bytes big-endian uint32][PCM data: num_samples * 2 bytes int16 LE]

"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TtsCommandType(str, Enum):
    """Command types sent to the TTS command socket."""

    SYNTHESIZE = "synthesize"
    STOP = "stop"
    SETTINGS = "settings"
    STATUS = "status"
    LIST_VOICES = "list_voices"


class TtsResponseType(str, Enum):
    """Response types from the TTS command socket."""

    SETTINGS_ACK = "settings_ack"
    STATUS = "status"
    VOICES = "voices"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Command TypedDicts
# ---------------------------------------------------------------------------


class SynthesizeCommand(TypedDict):
    type: Literal["synthesize"]
    content: str


class StopCommand(TypedDict):
    type: Literal["stop"]


class SettingsCommand(TypedDict):
    type: Literal["settings"]
    key: str
    value: Any


class StatusCommand(TypedDict):
    type: Literal["status"]


class ListVoicesCommand(TypedDict):
    type: Literal["list_voices"]


AnyTtsCommand = (
    SynthesizeCommand
    | StopCommand
    | SettingsCommand
    | StatusCommand
    | ListVoicesCommand
)


# ---------------------------------------------------------------------------
# Response TypedDicts
# ---------------------------------------------------------------------------


class SettingsAckResponse(TypedDict):
    type: Literal["settings_ack"]
    key: str
    ok: bool


class StatusResponse(TypedDict):
    type: Literal["status"]
    data: dict[str, Any]


class VoicesResponse(TypedDict):
    type: Literal["voices"]
    data: dict[str, dict[str, str]]


class TtsErrorResponse(TypedDict):
    type: Literal["error"]
    message: str


AnyTtsResponse = (
    SettingsAckResponse | StatusResponse | VoicesResponse | TtsErrorResponse
)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def tts_synthesize(text: str) -> SynthesizeCommand:
    """Create a synthesize command."""
    return {"type": "synthesize", "content": text}


def tts_stop() -> StopCommand:
    """Create a stop command."""
    return {"type": "stop"}


def tts_settings(key: str, value: Any) -> SettingsCommand:
    """Create a settings command."""
    return {"type": "settings", "key": key, "value": value}


# ---------------------------------------------------------------------------
# TTS audio frame binary constants
# ---------------------------------------------------------------------------

#: Size of the audio frame header (4 bytes for big-endian uint32)
AUDIO_FRAME_HEADER_SIZE: int = 4

#: NumPy / struct format for audio samples (little-endian int16)
AUDIO_SAMPLE_FORMAT: str = "<i2"

#: Number of bytes per audio sample (int16 = 2 bytes)
AUDIO_BYTES_PER_SAMPLE: int = 2

#: Default Kokoro sample rate in Hz
AUDIO_SAMPLE_RATE: int = 24000
