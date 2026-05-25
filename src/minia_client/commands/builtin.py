"""Built-in slash commands for minia_client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from minia_protocol import cmd_clear, cmd_compact

from minia_client.commands import Command, CommandRegistry


def _build_commands(
    on_exit: Callable[[], None],
    writer: Any,
    state: Any,
    ui: Any,
    on_status: Callable[[], str] | None = None,
) -> CommandRegistry:
    registry = CommandRegistry()

    # /help
    def _handle_help(ctx: dict, args: str) -> str | None:
        lines = ["Available commands:"]
        for cmd in ctx["registry"].list_commands():
            aliases_str = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  {cmd.name}{aliases_str}  —  {cmd.description}")
        lines.append("")
        lines.append("Keyboard shortcuts:")
        lines.append("  Ctrl+Q    Exit")
        lines.append("  Ctrl+O    Toggle focus (input/output)")
        lines.append("  Escape    Focus input field")
        lines.append("  Ctrl+Up/Down  Scroll output")
        lines.append("  PageUp/PageDown  Page scroll")
        lines.append("  Ctrl+End  Scroll to bottom")
        return "\n".join(lines)

    registry.register(
        Command(
            name="/help",
            aliases=["-h"],
            description="Show available commands",
            handler=_handle_help,
            usage="/help",
        )
    )

    # /clear
    async def _handle_clear(ctx: dict, args: str) -> str | None:
        if writer is not None:
            await writer.send(cmd_clear())
        state.history = []
        ui._fragments.clear()
        ui._invalidate()
        return "Conversation cleared."

    registry.register(
        Command(
            name="/clear",
            aliases=["-c"],
            description="Clear conversation history",
            handler=_handle_clear,
            usage="/clear",
        )
    )

    # /compact
    async def _handle_compact(ctx: dict, args: str) -> str | None:
        if writer is not None:
            await writer.send(cmd_compact())
        return "Context compaction requested."

    registry.register(
        Command(
            name="/compact",
            aliases=[],
            description="Compact conversation context",
            handler=_handle_compact,
            usage="/compact",
        )
    )

    # /status
    if on_status:

        def _handle_status(ctx: dict, args: str) -> str | None:
            return on_status() or "No status available."
    else:

        def _handle_status(ctx: dict, args: str) -> str | None:
            return "No status available."

    registry.register(
        Command(
            name="/status",
            aliases=[],
            description="Show connection status",
            handler=_handle_status,
            usage="/status",
        )
    )

    # /exit
    def _handle_exit(ctx: dict, args: str) -> str | None:
        on_exit()
        return None  # Exit is handled by the callback

    registry.register(
        Command(
            name="/exit",
            aliases=["-e", "quit", "q"],
            description="Exit the client",
            handler=_handle_exit,
            usage="/exit",
        )
    )

    return registry
