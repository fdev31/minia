from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import asyncio

from minia_protocol import EventType, event_to_dict


@dataclass
class ResponseData:
    type: EventType
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    task_instruction: str | None = None
    tool_schema: dict | None = None
    tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return event_to_dict(
            {
                "type": self.type.value,
                "content": self.content,
                "tool_name": self.tool_name,
                "tool_call_id": self.tool_call_id,
                "task_instruction": self.task_instruction,
                "tool_schema": self.tool_schema,
                "tokens": self.tokens,
            }
        )


@dataclass
class LlmContext:
    name: str
    model: str
    server_id: str | None = None
    tools_schema: list[dict] = field(default_factory=list)
    tool_executor: Callable[[str, dict], Awaitable[str]] | None = None
    history: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    unfolded_tools: dict[str, dict] = field(default_factory=dict)
    consecutive_empty: int = (
        0  # Track consecutive empty LLM responses for retry strategy
    )
    recent_tool_calls: list[tuple[str, str]] = field(
        default_factory=list
    )  # Track recent tool calls as (tool_name, args_hash)
    partial_text: str = field(
        default=""
    )  # Accumulated text during streaming, flushed to history on interrupt
    cancel_requested: asyncio.Event = field(
        default_factory=asyncio.Event,
        repr=False,
    )  # Set by server to cancel in-flight tool calls
    delegatee_ctx: "LlmContext | None" = (
        None  # Worker context set during delegation, for cancellation propagation
    )
