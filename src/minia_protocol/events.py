"""Event socket types (server → client).

The event socket broadcasts streaming LLM events and system notifications
to all connected clients.  Each event has a ``type`` field that identifies
its variant.

Usage
-----
On the server side::

    from minia_protocol import EventType, event_to_dict

    event: AnyEvent = {"type": EventType.TEXT, "content": "Hello"}
    await writer.send(json.dumps(event_to_dict(event)) + "\\n")

On the client side::

    from minia_protocol import EventType, AnyEvent

    def on_text(msg: AnyEvent) -> None:
        if msg["type"] == EventType.TEXT:
            content: str = msg["content"]
            ...

"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict


class EventType(str, Enum):
    """Event types broadcast over the event socket."""

    READY = "ready"
    USER_INPUT = "user_input"
    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL = "tool_call"
    FINAL = "final"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    CLEARED = "cleared"
    COMPACTION = "compaction"
    COMPACT_DONE = "compact_done"
    USAGE = "usage"
    CHECK = "check"
    TTS_STOP = "tts_stop"


# ---------------------------------------------------------------------------
# Event TypedDicts
# ---------------------------------------------------------------------------


class ReadyEvent(TypedDict):
    type: Literal["ready"]
    context_window: int
    main_model: str


class UserInputEvent(TypedDict):
    type: Literal["user_input"]
    content: str


class TextEvent(TypedDict):
    type: Literal["text"]
    content: str


class ThinkingEvent(TypedDict):
    type: Literal["thinking"]
    content: str


class ToolCallStartEvent(TypedDict):
    type: Literal["tool_call_start"]
    tool_name: str
    task_instruction: str | None
    tool_schema: dict | None


class ToolCallEvent(TypedDict):
    type: Literal["tool_call"]
    content: str
    tool_name: str | None
    tool_call_id: str | None


class FinalEvent(TypedDict):
    type: Literal["final"]
    content: str


class ErrorEvent(TypedDict):
    type: Literal["error"]
    message: str


class DisconnectedEvent(TypedDict):
    type: Literal["disconnected"]


class ClearedEvent(TypedDict):
    type: Literal["cleared"]


class CompactionEvent(TypedDict):
    type: Literal["compaction"]
    content: str


class CompactDoneEvent(TypedDict):
    type: Literal["compact_done"]


class UsageEvent(TypedDict):
    type: Literal["usage"]
    tokens: int


class TtsStopEvent(TypedDict):
    type: Literal["tts_stop"]


# Union type for discriminant narrowing
AnyEvent = (
    ReadyEvent
    | UserInputEvent
    | TextEvent
    | ThinkingEvent
    | ToolCallStartEvent
    | ToolCallEvent
    | FinalEvent
    | ErrorEvent
    | DisconnectedEvent
    | ClearedEvent
    | CompactionEvent
    | CompactDoneEvent
    | UsageEvent
    | TtsStopEvent
)


def event_to_dict(event: AnyEvent) -> dict[str, Any]:
    """Convert an event TypedDict to a JSON-serialisable dict."""
    return dict(event)
