"""minia_web — Web server for MinIA assistant.

A hybrid of minia_chatloop and minia_client that exposes the assistant
via a web interface with real-time messaging and audio playback.

Usage:
    minia-web
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from pathlib import Path
from typing import Any, Callable

from aiohttp import web
from minia_protocol import cmd_tts_stop, tts_synthesize
from minia_config import config

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


async def _run_event_client(
    socket_path: str,
    on_message: Callable[[dict], Any],
    stop_event: asyncio.Event,
) -> None:
    """Connect to the event socket and dispatch messages."""
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
                    on_message(msg)
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
                    "[Web] Reconnecting to %s in %.1fs (attempt %d)...",
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
                    "[Web] Cannot connect to %s: %s. Retrying in %.1fs...",
                    socket_path,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)


class TtsAudioClient:
    """Connect to the TTS audio socket and relay PCM frames."""

    def __init__(self, socket_path: str, on_frame: Any = None):
        self._socket_path = socket_path
        self._on_frame = on_frame
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to the TTS audio socket."""
        logger.info(
            "[TTS Audio] Connect called with socket path: %s", self._socket_path
        )
        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                self._socket_path
            )
            self._connected = True
            logger.info("[TTS Audio] Connected to %s", self._socket_path)
            self._task = asyncio.create_task(self._read_loop())
        except Exception as e:
            logger.error("[TTS Audio] Failed to connect: %s", e)

    async def close(self) -> None:
        """Close the connection."""
        logger.info("[TTS Audio] Close called - cancelling task")
        self._connected = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._writer:
            logger.info("[TTS Audio] Closing writer connection")
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    async def _read_loop(self) -> None:
        """Read audio frames from the TTS audio socket."""
        frame_count = 0
        while self._connected:
            assert self._reader
            try:
                # Read num_samples (4 bytes, big-endian uint32)
                num_samples_data = await self._reader.readexactly(4)
                if len(num_samples_data) < 4:
                    await asyncio.sleep(0.1)
                    continue
                num_samples = struct.unpack("!I", num_samples_data)[0]

                # Read PCM data (num_samples * 2 bytes for int16)
                if num_samples > 0:
                    pcm_data = await self._reader.readexactly(num_samples * 2)
                    if len(pcm_data) < num_samples * 2:
                        break
                    # Send frame to handler
                    if self._on_frame:
                        await self._on_frame(pcm_data, num_samples)
                else:
                    await asyncio.sleep(0.01)
                frame_count += 1
                if frame_count % 100 == 0:
                    duration = num_samples / 16000.0
                    logger.info(
                        "[TTS Audio] Frame %d received: %d samples, %.3fs duration",
                        frame_count,
                        num_samples,
                        duration,
                    )
            except (
                asyncio.IncompleteReadError,
                ConnectionError,
                asyncio.CancelledError,
            ):
                break
            except Exception as e:
                logger.error("[TTS Audio] Error: %s", e)
                await asyncio.sleep(0.1)
        logger.info("[TTS Audio] Read loop ended after %d frames", frame_count)


def _remove_stale_clients(clients: set, ws: web.WebSocketResponse) -> None:
    """Remove a WebSocket client that failed to send."""
    try:
        clients.discard(ws)
    except Exception:
        pass


class MiniaWebServer:
    """Main web server for MinIA."""

    def __init__(self):
        logger.info(
            "[Web] Initializing with event=%s, command=%s, audio=%s",
            config.default.event_socket_path,
            config.default.cmd_socket_path,
            config.tts.audio_socket_path,
        )
        self._cmd_client = config.default.cmd_socket_path
        self._tts_cmd_client = config.tts.cmd_socket_path
        self._tts_audio_client = TtsAudioClient(
            config.tts.audio_socket_path, self._on_tts_frame
        )
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._app = web.Application()
        self._setup_routes()
        self._event_stop = asyncio.Event()

    def _setup_routes(self) -> None:
        """Set up aiohttp routes."""
        self._app.router.add_get("/", self._serve_index)
        self._app.router.add_static("/static/", path=str(STATIC_DIR), name="static")
        self._app.router.add_get("/ws", self._handle_websocket)

    async def _serve_index(self, request: web.Request) -> web.FileResponse:
        """Serve the main index.html."""
        logger.info("[Web] Serving index page")
        return web.FileResponse(STATIC_DIR / "index.html")

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection from browser."""
        logger.info("[Web] WebSocket connected from %s", request.remote)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        logger.info("[Web] Client connected. Total clients: %d", len(self._ws_clients))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        msg_type = data.get("type")
                        logger.info("[Web] Received command: %s", msg_type)
                        if msg_type == "input":
                            text = data.get("text", "")
                            logger.info("[Web] Input text: %s", text[:100])
                            await self._send_command(self._cmd_client, data)
                        elif msg_type == "tts_speak":
                            text = data.get("content", "")
                            logger.info("[Web] TTS speak: %s", text[:100])
                            await self._send_command(
                                self._tts_cmd_client,
                                tts_synthesize(text),
                            )
                        elif msg_type == "tts_stop":
                            logger.info("[Web] TTS stop requested")
                            await self._send_command(
                                self._tts_cmd_client, cmd_tts_stop()
                            )
                    except json.JSONDecodeError:
                        logger.warning("[Web] Invalid JSON from client")
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("[Web] WebSocket error: %s", ws.exception())
        finally:
            self._ws_clients.discard(ws)
            logger.info(
                "[Web] Client disconnected. Total clients: %d", len(self._ws_clients)
            )
        return ws

    async def _send_command(self, socket_path: str, msg: dict) -> None:
        """Fire-and-forget: open a Unix socket, send JSON, close."""
        try:
            reader, writer = await asyncio.open_unix_connection(socket_path)
            writer.write((json.dumps(msg) + "\n").encode())
            await writer.drain()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        except Exception as e:
            logger.error("[Web] Failed to send command %s: %s", msg.get("type"), e)

    async def _on_tts_frame(self, pcm_data: bytes, num_samples: int) -> None:
        """Relay TTS audio frame to all connected browser clients."""
        if not self._ws_clients:
            logger.info(
                "[Web] No audio clients, dropping TTS frame (%d samples)", num_samples
            )
            return
        logger.debug("[Web] Relaying TTS frame: %d samples", num_samples)
        frame = struct.pack("!I", num_samples) + pcm_data
        for ws in list(self._ws_clients):
            try:
                await ws.send_bytes(frame)
            except Exception:
                _remove_stale_clients(self._ws_clients, ws)

    async def _handle_event_message(self, msg: dict) -> None:
        """Relay event socket messages to all connected browser clients."""
        msg_type = msg.get("type", "unknown")
        logger.info(
            "[Web] Relaying event: %s to %d clients", msg_type, len(self._ws_clients)
        )
        if not self._ws_clients:
            return

        message = json.dumps(msg)
        for ws in list(self._ws_clients):
            try:
                await ws.send_str(message)
            except Exception:
                _remove_stale_clients(self._ws_clients, ws)

    async def start(self) -> web.AppRunner:
        """Start the web server."""
        logger.info("[Web] Starting server on 0.0.0.0:9999")
        self._event_task = asyncio.create_task(
            _run_event_client(
                config.default.event_socket_path,
                self._handle_event_message,
                self._event_stop,
            )
        )
        await self._tts_audio_client.connect()
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 9999)
        await site.start()
        logger.info("[Web] Server started on port 9999")
        return runner

    async def stop(self) -> None:
        """Stop the web server."""
        logger.info("[Web] Stopping server")
        self._event_stop.set()
        await self._tts_audio_client.close()


async def _main() -> None:
    """Main entry point."""
    server = MiniaWebServer()
    runner = await server.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()
        await server.stop()


def main() -> None:
    """Entry point for minia-web."""
    from minia_utils.logging import configure_logging

    configure_logging(log_level=config.default.log_level or "INFO", add_console=True)
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
