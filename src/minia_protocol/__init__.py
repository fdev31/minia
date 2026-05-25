"""Shared protocol types for all minia socket interfaces.

Provides enums, TypedDicts, and factory helpers for:

- Event socket (server → client): ``EventType``, ``event_to_dict()``
- Command socket (client → server): ``cmd_input()``, ``cmd_clear()``, ``cmd_compact()``
- TTS command socket (client → server): ``tts_synthesize()``, ``tts_stop()``, ``tts_settings()``
- TTS audio frame binary constants

All consumers should import from this package rather than using magic strings.

"""

from __future__ import annotations

from .commands import (
    AnyCommand,
    ClearCommand,
    CompactCommand,
    CommandType,
    DisconnectCommand,
    InputCommand,
    SubscribeCommand,
    TtsStopCommand,
    cmd_clear,
    cmd_compact,
    cmd_input,
    cmd_tts_stop,
)
from .events import (
    AnyEvent,
    ClearedEvent,
    CompactDoneEvent,
    CompactionEvent,
    DisconnectedEvent,
    ErrorEvent,
    EventType,
    FinalEvent,
    ReadyEvent,
    TextEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolCallStartEvent,
    TtsStopEvent,
    UsageEvent,
    UserInputEvent,
    event_to_dict,
)
from .tts import (
    AnyTtsCommand,
    AnyTtsResponse,
    ListVoicesCommand,
    SettingsAckResponse,
    SettingsCommand,
    StatusCommand,
    StatusResponse,
    SynthesizeCommand,
    StopCommand,
    TtsCommandType,
    TtsErrorResponse,
    TtsResponseType,
    VoicesResponse,
    tts_settings,
    tts_stop,
    tts_synthesize,
)

__all__ = [
    # --- events ---
    "EventType",
    "AnyEvent",
    "event_to_dict",
    "ReadyEvent",
    "UserInputEvent",
    "TextEvent",
    "ThinkingEvent",
    "ToolCallStartEvent",
    "ToolCallEvent",
    "FinalEvent",
    "ErrorEvent",
    "DisconnectedEvent",
    "ClearedEvent",
    "CompactionEvent",
    "CompactDoneEvent",
    "UsageEvent",
    "TtsStopEvent",
    # --- commands ---
    "CommandType",
    "AnyCommand",
    "cmd_input",
    "cmd_clear",
    "cmd_compact",
    "cmd_tts_stop",
    "InputCommand",
    "ClearCommand",
    "CompactCommand",
    "TtsStopCommand",
    "DisconnectCommand",
    "SubscribeCommand",
    # --- tts ---
    "TtsCommandType",
    "TtsResponseType",
    "AnyTtsCommand",
    "AnyTtsResponse",
    "tts_synthesize",
    "tts_stop",
    "tts_settings",
    "SynthesizeCommand",
    "StopCommand",
    "SettingsCommand",
    "ListVoicesCommand",
    "StatusCommand",
    "SettingsAckResponse",
    "StatusResponse",
    "VoicesResponse",
    "TtsErrorResponse",
    # --- tts audio constants ---
    "AUDIO_FRAME_HEADER_SIZE",
    "AUDIO_SAMPLE_FORMAT",
    "AUDIO_BYTES_PER_SAMPLE",
    "AUDIO_SAMPLE_RATE",
]
