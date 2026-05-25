"""Command socket types (client → server).

The command socket accepts fire-and-forget commands from clients to the
main minia server.

Usage
-----
::

    from minia_protocol import cmd_input, cmd_clear, cmd_compact

    await writer.send(cmd_input("Hello"))
    await writer.send(cmd_clear())

"""

from __future__ import annotations

from enum import Enum
from typing import Literal, TypedDict


class CommandType(str, Enum):
    """Command types sent to the minia command socket."""

    INPUT = "input"
    CLEAR = "clear"
    TTS_STOP = "tts_stop"
    COMPACT = "compact"
    DISCONNECT = "disconnect"
    SUBSCRIBE = "subscribe"


# ---------------------------------------------------------------------------
# Command TypedDicts
# ---------------------------------------------------------------------------


class InputCommand(TypedDict):
    type: Literal["input"]
    content: str


class ClearCommand(TypedDict):
    type: Literal["clear"]


class TtsStopCommand(TypedDict):
    type: Literal["tts_stop"]


class CompactCommand(TypedDict):
    type: Literal["compact"]


class DisconnectCommand(TypedDict):
    type: Literal["disconnect"]


class SubscribeCommand(TypedDict):
    type: Literal["subscribe"]


AnyCommand = (
    InputCommand
    | ClearCommand
    | TtsStopCommand
    | CompactCommand
    | DisconnectCommand
    | SubscribeCommand
)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def cmd_input(text: str) -> InputCommand:
    """Create an input command."""
    return {"type": "input", "content": text}


def cmd_clear() -> ClearCommand:
    """Create a clear command."""
    return {"type": "clear"}


def cmd_compact() -> CompactCommand:
    """Create a compact command."""
    return {"type": "compact"}


def cmd_tts_stop() -> TtsStopCommand:
    """Create a TTS stop command."""
    return {"type": "tts_stop"}
