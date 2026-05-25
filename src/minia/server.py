"""Unix socket server for command and event communication."""

import asyncio
import json
import signal
import time
import uuid

from minia.agent import Agent
from minia_config import config
from minia_protocol import EventType
from minia_sockets.server import SOCKET_DISCONNECT_ERRORS
from .llm_client import TimeoutError, ConnectionError
from . import compaction
from minia_utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Broadcast helper
# ---------------------------------------------------------------------------


async def _broadcast(clients: list, msg: dict) -> None:
    """Send a JSON-lines message to all clients, removing stale ones."""
    data = (json.dumps(msg) + "\n").encode()
    stale = []
    for i, client in enumerate(clients):
        try:
            _, writer, _ = client
            writer.write(data)
            await writer.drain()
        except SOCKET_DISCONNECT_ERRORS:
            stale.append(i)
    for j in reversed(stale):
        clients.pop(j)


# ---------------------------------------------------------------------------
# Command socket: fire-and-forget
# ---------------------------------------------------------------------------


async def _handle_command(
    reader,
    writer,
    clients: list,
    queue: asyncio.Queue,
    agents: list[Agent],
) -> None:
    logger.info("[Cmd] Client connected")
    try:
        line = await reader.readline()
        if not line:
            return
        msg = json.loads(line)
        msg_type = msg.get("type", "")
        if msg_type == "input":
            content = msg.get("content", "")
            await _broadcast(clients, {"type": "user_input", "content": content})
            await queue.put((time.monotonic(), content))
        elif msg_type == "clear":
            for a in agents:
                a.context.history = [a.context.history[0]]
            await _broadcast(clients, {"type": "cleared"})
        elif msg_type == "tts_stop":
            await _broadcast(clients, {"type": "tts_stop"})
        elif msg_type == "compact":
            summary = await compaction.compact_history(agents[0].context, force=True)
            if summary:
                await _broadcast(clients, {"type": "compaction", "content": summary})
    except json.JSONDecodeError:
        pass
    except Exception as e:
        if not isinstance(e, json.JSONDecodeError):
            logger.warning("[Cmd] Error: %s", e)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Event socket: persistent subscription
# ---------------------------------------------------------------------------


async def _handle_event_client(reader, writer, clients: list, client_id: str) -> None:
    logger.info("[Event] Client connected | id=%s", client_id)
    clients.append((reader, writer, client_id))
    try:
        await _broadcast(
            clients,
            {
                "type": "ready",
                "context_window": config.llm.context_window,
                "main_model": config.llm.main_model,
            },
        )
    except Exception as e:
        logger.warning("[Event] Failed 'ready' to %s: %s", client_id, e)

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                if msg.get("type") == "tts_stop":
                    await _broadcast(clients, {"type": "tts_stop"})
                elif msg.get("type") == "disconnect":
                    break
            except json.JSONDecodeError:
                pass
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            clients.remove((reader, writer, client_id))
        except ValueError:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("[Event] Client disconnected | remaining=%d", len(clients))


# ---------------------------------------------------------------------------
# Queue draining helper
# ---------------------------------------------------------------------------


async def _drain_queue_and_broadcast(queue, clients, max_age: float = 2.0):
    """Drain all pending messages, broadcast them, return recent ones.

    Messages older than *max_age* seconds are discarded after broadcasting.
    Recent messages (within the window) are broadcast and returned for re-queuing.
    """
    now = time.monotonic()
    recent: list[str] = []
    while True:
        try:
            timestamp, content = queue.get_nowait()
            await _broadcast(clients, {"type": "user_input", "content": content})
            if now - timestamp <= max_age:
                recent.append(content)
        except asyncio.QueueEmpty:
            break
    return recent


# ---------------------------------------------------------------------------
# Interrupt handler
# ---------------------------------------------------------------------------


def _flush_partial_text(agent: Agent) -> None:
    """Flush any partial text accumulated during streaming to history.

    Called when a new message interrupts the current streaming response.
    The partial text becomes an assistant message in history so the agent
    can acknowledge the interruption contextually.
    """
    partial = agent.context.partial_text
    if partial:
        agent.context.history.append({"role": "assistant", "content": partial})
        agent.context.partial_text = ""
        logger.info("[Server] Flushed partial response (%d chars)", len(partial))


async def _interrupt_and_requeue(queue, clients, agents, reason: str):
    """Handle interruption: flush partial text, drain queue, re-queue recent messages.

    Returns True if there are messages to process next, False if queue is empty.
    """
    logger.info("[Server] Interrupting: %s", reason)
    # Signal in-flight tool calls to cancel
    agents[0].context.cancel_requested.set()
    _flush_partial_text(agents[0])
    recent = await _drain_queue_and_broadcast(queue, clients)
    for msg in recent:
        await queue.put((time.monotonic(), msg))
    return bool(recent)


# ---------------------------------------------------------------------------
# Processing loop
# ---------------------------------------------------------------------------


async def process_loop(queue: asyncio.Queue, clients: list, agents: list[Agent]):
    while True:
        _, content = await queue.get()
        logger.info("[Server] Processing input")
        try:
            chunk_count = 0
            t0 = time.monotonic()
            async for chunk in agents[0].run_streaming(content):
                # Check for new messages during streaming
                if not queue.empty():
                    if not await _interrupt_and_requeue(
                        queue, clients, agents, "new message"
                    ):
                        break
                    continue

                if chunk.type == EventType.CHECK:
                    if not queue.empty():
                        if not await _interrupt_and_requeue(
                            queue, clients, agents, "message during CHECK"
                        ):
                            break
                        continue

                await _broadcast(clients, chunk.to_dict())
                chunk_count += 1

            logger.info(
                "[Server] Streaming complete | chunks=%d ms=%.1f",
                chunk_count,
                (time.monotonic() - t0) * 1000,
            )
        except asyncio.CancelledError:
            # Tool execution was cancelled by interrupt — clear the flag
            agents[0].context.cancel_requested.clear()
            logger.info("[Server] Streaming interrupted by tool cancellation")
        except ConnectionError as e:
            logger.exception("[Server] LLM connection error: %s", e)
            await _broadcast(
                clients,
                {
                    "type": "error",
                    "message": "LLM server is not reachable. Please check if the server is running.",
                },
            )
        except TimeoutError as e:
            logger.exception("[Server] LLM timeout: %s", e)
            await _broadcast(
                clients,
                {
                    "type": "error",
                    "message": "LLM server request timed out. Please try again.",
                },
            )
        except Exception as e:
            logger.exception("[Server] Error: %s", e)
            await _broadcast(clients, {"type": "error", "message": str(e)})
        finally:
            # Always clear the cancel flag after processing completes or is interrupted
            agents[0].context.cancel_requested.clear()


# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------


async def _run_socket_server(socket_path: str, handler, stop: asyncio.Future) -> None:
    """Start a Unix socket server and wait for shutdown."""
    loop = asyncio.get_running_loop()

    def _shutdown():
        if not stop.done():
            stop.set_result(True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    server = await asyncio.start_unix_server(handler, socket_path)
    logger.info("Listening on %s", socket_path)

    try:
        await stop
    finally:
        server.close()
        await server.wait_closed()


async def run_server(
    agents: list[Agent],
    cmd_socket_path: str | None = None,
    event_socket_path: str | None = None,
) -> None:
    if cmd_socket_path is None:
        cmd_socket_path = config.default.cmd_socket_path
    if event_socket_path is None:
        event_socket_path = config.default.event_socket_path

    logger.info(
        "[Server] Starting | cmd=%s | events=%s", cmd_socket_path, event_socket_path
    )

    clients: list = []
    queue: asyncio.Queue = asyncio.Queue()

    def cmd_handler(r, w):
        return _handle_command(r, w, clients, queue, agents)

    def event_handler(r, w):
        return _handle_event_client(r, w, clients, str(uuid.uuid4())[:8])

    process_task = asyncio.create_task(process_loop(queue, clients, agents))

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    try:
        await asyncio.gather(
            _run_socket_server(cmd_socket_path, cmd_handler, stop),
            _run_socket_server(event_socket_path, event_handler, stop),
            return_exceptions=True,
        )
    finally:
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass
        logger.info("[Server] Shutdown complete")
