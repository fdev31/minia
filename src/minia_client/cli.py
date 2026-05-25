#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ['rich', 'prompt_toolkit']
# ///
"""minia_client — terminal chat client for MinIA.

Connects to Unix domain sockets for commands and events:
- Command socket: fire-and-forget (send input, clear, etc.)
- Event socket: persistent subscription (receive streaming responses)
"""

from __future__ import annotations

import asyncio
import json
import signal

from rich.console import Console
from minia_client.logger import logger
from typing import Any, Callable

from minia_client.ui import ChatUI
from minia_client.commands.builtin import _build_commands
from minia_config import config
from minia_protocol import EventType, cmd_input
from minia_sockets.server import open_unix

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class ClientState:
    """Shared state for the client."""

    def __init__(self) -> None:
        self.history: list[tuple[str, str]] = []
        self.current_response: str = ""
        self.tool_status: str = ""
        self.error: str = ""
        self.disconnected: bool = False
        self.ready: bool = False
        self.busy: bool = False
        self.token_used: int = 0
        self.token_total: int = 32000
        self.socket_path: str = ""

    def add_user_message(self, content: str) -> None:
        if self.current_response:
            self.history.append(("assistant", self.current_response))
            self.current_response = ""
        self.history.append(("user", content))

    def append_response(self, text: str) -> None:
        self.current_response += text

    def set_disconnected(self) -> None:
        self.disconnected = True


# ---------------------------------------------------------------------------
# Slash command dispatch
# ---------------------------------------------------------------------------

_EXIT_REQUESTED = False


def _request_exit() -> None:
    global _EXIT_REQUESTED
    _EXIT_REQUESTED = True


async def _handle_command(
    text: str,
    state: ClientState,
    ui: ChatUI,
    cmd_sender: Any,
) -> bool:
    """Dispatch a slash command. Returns True if the command was handled."""
    if not text.startswith("/"):
        return False

    registry = _build_commands(
        on_exit=_request_exit,
        writer=cmd_sender,
        state=state,
        ui=ui,
    )

    parts = text.split(None, 1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    cmd = registry.lookup(cmd_name)
    if cmd is None:
        ui.append_error(
            f"Unknown command: {cmd_name}. Type /help for available commands."
        )
        ui._invalidate()
        return True

    if cmd.handler is None:
        ui.append_event(f"Command {cmd_name} has no handler.")
        ui._invalidate()
        return True

    ctx = {"registry": registry, "writer": cmd_sender}
    result = cmd.handler(ctx, args)
    if asyncio.iscoroutine(result):
        result = await result
    if result is not None:
        ui.append_event(result)
        ui._invalidate()

    # /exit handled via callback
    return True


# ---------------------------------------------------------------------------
# Socket I/O
# ---------------------------------------------------------------------------


async def _run_event_client(
    socket_path: str,
    handlers: dict[str, Callable[[dict], Any]],
    stop_event: asyncio.Event,
) -> None:
    """Connect to the event socket and dispatch messages to handlers."""
    reconnect_count = 0

    while not stop_event.is_set():
        try:
            reader, writer = await asyncio.open_unix_connection(socket_path)
            reconnect_count = 0

            while not stop_event.is_set():
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                    handler = handlers.get(msg.get("type", ""))
                    if handler:
                        handler(msg)
                except json.JSONDecodeError:
                    pass

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            if not stop_event.is_set():
                delay = min(2.0 * (2**reconnect_count), 30.0)
                reconnect_count += 1
                logger.warning(
                    "Reconnecting to %s in %.1fs (attempt %d)...",
                    socket_path,
                    delay,
                    reconnect_count,
                )
                await asyncio.sleep(delay)

        except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
            if not stop_event.is_set():
                delay = min(2.0 * (2**reconnect_count), 30.0)
                reconnect_count += 1
                logger.warning(
                    "Cannot connect to %s: %s. Retrying in %.1fs...",
                    socket_path,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)


class CommandSender:
    """Fire-and-forget command sender for the minia command socket."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path

    async def send_line(self, msg: dict) -> None:
        """Send a command and close."""
        logger.debug("[Client] Sending: %s", json.dumps(msg)[:200])
        async with open_unix(self._socket_path) as (reader, writer):
            writer.write((json.dumps(msg) + "\n").encode())
            await writer.drain()

    async def send(self, msg: dict) -> None:
        """Alias for send_line."""
        await self.send_line(msg)


def _make_message_handlers(
    state: ClientState,
    ui: ChatUI,
) -> dict[str, Callable[[dict], Any]]:
    """Create message handlers that update state and UI."""

    def on_ready(msg: dict) -> None:
        state.ready = True
        state.disconnected = False
        # Update token_total from server info if available
        if "context_window" in msg:
            state.token_total = msg["context_window"]
            ui.set_token_count(state.token_used, state.token_total)

    def on_text(msg: dict) -> None:
        content = msg.get("content", "")
        if not state.busy:
            state.busy = True
            state.current_response = ""
            ui.begin_llm_response()
        state.append_response(content)
        ui.append_llm_token(content)

    def on_thinking(msg: dict) -> None:
        content = msg.get("content", "")
        if not state.busy:
            state.busy = True
            state.current_response = ""
            ui.begin_llm_response()
        ui.append_thinking(content)

    def on_tool_call_start(msg: dict) -> None:
        tool_name = msg.get("tool_name", "")
        task_instruction = msg.get("task_instruction")
        tool_schema = msg.get("tool_schema")
        state.tool_status = tool_name
        if task_instruction:
            ui.append_tool(f"Running: {tool_name}: {task_instruction}")
        else:
            ui.append_tool(f"Running: {tool_name}...")
        if tool_schema:
            func = tool_schema.get("function", {})
            params = func.get("parameters", {})
            properties = params.get("properties", {})
            if properties:
                ui.append_event(
                    f"Schema: {func.get('name', tool_name)} "
                    f"- {func.get('description', '')}"
                )
                for pname, pdesc in properties.items():
                    desc = (
                        pdesc.get("description", "") if isinstance(pdesc, dict) else ""
                    )
                    ui.append_event(f"  • {pname}: {desc}")

    def on_tool_call(msg: dict) -> None:
        content = msg.get("content", "")
        state.tool_status = content
        ui.append_tool(f"Result: {content}")

    def on_final(msg: dict) -> None:
        content = msg.get("content", "")
        if state.current_response:
            state.history.append(("assistant", state.current_response))
        state.current_response = ""
        state.busy = False
        state.tool_status = ""
        ui.finalize_llm_response(content)

    def on_error(msg: dict) -> None:
        state.error = msg.get("message", "Unknown error")
        ui.append_error(state.error)
        state.busy = False

    def on_disconnected(msg: dict) -> None:
        state.set_disconnected()

    def on_user_input(msg: dict) -> None:
        ui.append_user(msg.get("content", ""))

    def on_cleared(msg: dict) -> None:
        state.history = []
        ui._fragments.clear()
        ui._invalidate()

    def on_compaction(msg: dict) -> None:
        content = msg.get("content", "")
        if state.busy:
            ui.finalize_llm_response(state.current_response)
            state.busy = False
            state.current_response = ""
        state.busy = True
        state.current_response = ""
        ui.begin_llm_response()
        ui.append_llm_token(content)
        ui.finalize_llm_response(state.current_response)
        state.busy = False
        state.current_response = ""

    def on_compact_done(msg: dict) -> None:
        ui.append_event("Context compaction complete.")

    def on_usage(msg: dict) -> None:
        state.token_used = msg.get("tokens", state.token_used)
        ui.set_token_count(state.token_used, state.token_total)

    return {
        EventType.READY.value: on_ready,
        EventType.TEXT.value: on_text,
        EventType.THINKING.value: on_thinking,
        EventType.TOOL_CALL_START.value: on_tool_call_start,
        EventType.TOOL_CALL.value: on_tool_call,
        EventType.FINAL.value: on_final,
        EventType.ERROR.value: on_error,
        EventType.DISCONNECTED.value: on_disconnected,
        EventType.USER_INPUT.value: on_user_input,
        EventType.CLEARED.value: on_cleared,
        EventType.COMPACTION.value: on_compaction,
        EventType.COMPACT_DONE.value: on_compact_done,
        EventType.USAGE.value: on_usage,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _main() -> None:
    console = Console()
    event_socket_path = config.default.event_socket_path
    cmd_socket_path = config.default.cmd_socket_path
    state = ClientState()
    state.socket_path = event_socket_path

    console.print("\n[blue]minia-client[/blue] — Your mini AI client", soft_wrap=True)
    console.print(f"Connecting to [cyan]{event_socket_path}[/cyan]...", soft_wrap=True)

    async def on_submit(text: str) -> None:
        if _EXIT_REQUESTED:
            return
        if not text or not text.strip():
            return

        # Try slash command first
        if text.startswith("/"):
            await _handle_command(text, state, ui, cmd_sender)
            return

        # Regular message — send to command socket
        logger.debug("[Client] Sending: %s", text[:200])
        await cmd_sender.send_line(cmd_input(text))

    def on_exit() -> None:
        _request_exit()

    ui = ChatUI(on_submit=on_submit, on_exit=on_exit)
    ui.set_event_loop(asyncio.get_event_loop())
    cmd_sender = CommandSender(cmd_socket_path)

    # Register message handlers
    handlers = _make_message_handlers(state, ui)

    # Start event socket reader + reconnect loop
    stop_event = asyncio.Event()
    event_task = asyncio.create_task(
        _run_event_client(event_socket_path, handlers, stop_event)
    )

    # Run the UI
    try:
        await ui.run_async()
    except KeyboardInterrupt:
        pass
    finally:
        _request_exit()
        stop_event.set()
        event_task.cancel()
        try:
            await event_task
        except asyncio.CancelledError:
            pass

    logger.info("[Client] Disconnected")


class _ExitRequested(Exception):
    """Raised when the user requests exit."""

    pass


def _signal_handler(signum: int, frame: object) -> None:
    _request_exit()


def main() -> None:
    """Entry point for the minia_client command."""
    from minia_utils.logging import configure_logging, resolve_log_level

    configure_logging(
        log_level=resolve_log_level(config, "client"),
        add_console=False,
    )
    # Handle SIGINT/SIGTERM gracefully
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
