"""Unix socket TTS server using Kokoro.

Splits into two sockets:
- Command socket: fire-and-forget (synthesize text, stop, settings)
- Audio socket: broadcast raw audio frames to all connected clients
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import struct
from pathlib import Path
from typing import Any

from minia_protocol import TtsCommandType
from minia_sockets.server import SOCKET_DISCONNECT_ERRORS
from minia_tts.kokoro.constants import SAMPLE_RATE
from minia_tts.protocol import TTSConfig, TTSState
from minia_config import config as global_config
from minia_tts.kokoro.provider import KokoroTTSProvider
from minia_tts.output.base import AudioOutput
from minia_tts.kokoro.constants import KOKORO_VOICES, KOKORO_TO_ISO
from minia_tts.cancellation import CancellationToken


logger = logging.getLogger(__name__)


async def create_provider(config: Any) -> KokoroTTSProvider:
    """Create and warm up the Kokoro TTS provider."""
    provider = KokoroTTSProvider(
        voice=config.voice,
        language=config.language,
        speed=config.speed,
        volume=config.volume,
    )
    await provider.start()
    return provider


def create_output(mode: str, sample_rate: int) -> AudioOutput | None:
    """Create the playback output backend based on mode."""
    if mode not in ("playback", "both"):
        return None

    try:
        import sounddevice  # type: ignore[import-untyped]  # noqa: F401
        from minia_tts.output.playback import PlaybackOutput

        return PlaybackOutput(sample_rate=sample_rate)
    except ImportError:
        if mode == "playback":
            logger.error(
                "sounddevice not available, install with: pip install sounddevice"
            )
        else:
            logger.warning("sounddevice not available, falling back to stream-only")
        return None


# ---------------------------------------------------------------------------
# Broadcast helper
# ---------------------------------------------------------------------------


async def _broadcast_audio(clients: list, frame: bytes) -> None:
    """Send an audio frame to all connected audio socket clients."""
    stale = []
    for i, client in enumerate(clients):
        try:
            _, writer = client
            writer.write(frame)
            await writer.drain()
        except SOCKET_DISCONNECT_ERRORS:
            stale.append(i)
    for j in reversed(stale):
        clients.pop(j)


# ---------------------------------------------------------------------------
# Command socket: fire-and-forget (synthesize/stop) or request-response (status/settings)
# ---------------------------------------------------------------------------


async def _send_response(writer: asyncio.StreamWriter, msg: dict) -> None:
    """Send a JSON response back to the client."""
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()


async def _handle_command_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: TTSState,
    audio_clients: list,
) -> None:
    """Handle a command socket client."""
    logger.info("[TTS Cmd] Client connected")
    try:
        line = await reader.readline()
        if not line:
            logger.info("[TTS Cmd] Empty line, closing")
            return

        msg = json.loads(line)
        cmd_type = msg.get("type", "")

        if cmd_type == TtsCommandType.SYNTHESIZE.value:
            text = msg.get("content", "")
            logger.info("[TTS Cmd] Synthesize: '%s'", text[:50])
            await _synthesize_and_broadcast(state, text, audio_clients)
        elif cmd_type == TtsCommandType.STOP.value:
            logger.info("[TTS Cmd] Stop")
            state.synthesis._cancellation.cancel()
            await state.provider.stop()
            state.provider._cancellation = CancellationToken()
            if state.output_playback:
                await state.output_playback.stop()
            state.synthesis.speaking = False
            state.synthesis.current_text = ""
        elif cmd_type == TtsCommandType.SETTINGS.value:
            key = msg.get("key", "")
            value = msg.get("value")
            result = await _apply_settings(state, key, value)
            await _send_response(
                writer, {"type": "settings_ack", "key": key, "ok": result}
            )
        elif cmd_type == TtsCommandType.STATUS.value:
            status = {
                "speaking": state.synthesis.speaking,
                "voice": state.config.voice,
                "language": state.config.language,
                "speed": state.config.speed,
                "volume": state.config.volume,
                "output_mode": state.config.output_mode,
                "current_text": state.synthesis.current_text,
            }
            await _send_response(writer, {"type": "status", "data": status})
        elif cmd_type == TtsCommandType.LIST_VOICES.value:
            voices = {}
            for voice in KOKORO_VOICES:
                lang_code = voice[0]
                gender = voice[1]
                lang = KOKORO_TO_ISO.get(lang_code, "unknown")
                voices[voice] = {"gender": gender, "language": lang}
            await _send_response(writer, {"type": "voices", "data": voices})
    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.warning("[TTS Cmd] Error: %s", e)
        try:
            await _send_response(writer, {"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("[TTS Cmd] Client closed")


# ---------------------------------------------------------------------------
# Audio socket: broadcast raw audio frames
# ---------------------------------------------------------------------------


def _pack_audio_frame(audio_chunk: Any) -> bytes:
    """Pack audio chunk into frame: [num_samples:4][int16 PCM data]."""
    audio_int16 = audio_chunk.astype("<i2")
    num_samples = len(audio_int16)
    return struct.pack("!I", num_samples) + audio_int16.tobytes()


async def _handle_audio_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    audio_clients: list,
) -> None:
    """Handle an audio socket client (persistent subscription)."""
    client = (reader, writer)
    audio_clients.append(client)
    logger.info("[TTS Audio] Client connected | count=%d", len(audio_clients))

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                if msg.get("type") == "disconnect":
                    break
            except json.JSONDecodeError:
                pass
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            audio_clients.remove(client)
        except ValueError:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("[TTS Audio] Client disconnected | count=%d", len(audio_clients))


# ---------------------------------------------------------------------------
# Synthesis with audio broadcast
# ---------------------------------------------------------------------------


async def _synthesize_and_broadcast(
    state: TTSState, text: str, audio_clients: list
) -> None:
    """Synthesize text and broadcast audio frames to all audio socket clients."""

    logger.info("[TTS] Synthesis started: '%s'", text[:200])
    state.synthesis.speaking = True
    state.synthesis.current_text = text
    state.synthesis._cancellation = CancellationToken()
    if state.output_playback:
        state.output_playback.reset_stopped()

    chunk_count = 0
    cancelled = False
    try:
        async for audio_chunk in state.provider.speak_streamed(text):
            if state.synthesis._cancellation.__class__.__name__ == "CancelledEvent" or (
                hasattr(state.synthesis._cancellation, "is_cancelled")
                and state.synthesis._cancellation.is_cancelled
            ):
                cancelled = True
                break
            if len(audio_chunk) == 0:
                continue
            # Playback
            if state.output_playback:
                try:
                    await state.output_playback.play(audio_chunk, SAMPLE_RATE)
                except Exception:
                    logger.exception("[TTS] Playback error")
            # Broadcast to audio socket clients
            frame = _pack_audio_frame(audio_chunk)
            await _broadcast_audio(audio_clients, frame)
            chunk_count += 1
            logger.debug(
                "[TTS] Audio chunk %d processed (%d samples)",
                chunk_count,
                len(audio_chunk),
            )
    except Exception as e:
        logger.error("Synthesis error: %s", e)
        cancelled = True
    finally:
        state.synthesis.speaking = False
        state.synthesis.current_text = ""
        if cancelled:
            logger.info("[TTS] Synthesis cancelled after %d chunks", chunk_count)
        else:
            logger.info("[TTS] Synthesis completed: %d chunks", chunk_count)


async def _apply_settings(state: TTSState, key: str, value: Any) -> bool:
    """Apply a settings change. Returns True on success."""

    if key == "voice":
        voice_lookup = {v[3:]: v for v in KOKORO_VOICES}
        if value in voice_lookup:
            full_name = voice_lookup[value]
            state.config.voice = full_name
            state.provider.set_voice(full_name)
            return True
        return False
    elif key == "language":
        state.config.language = value
        state.provider.set_language(value)
        return True
    elif key == "speed":
        try:
            speed = float(value)
            state.config.speed = speed
            state.provider.set_speed(speed)
            return True
        except (ValueError, TypeError):
            return False
    elif key == "volume":
        try:
            volume = float(value)
            state.config.volume = volume
            state.provider.set_volume(volume)
            return True
        except (ValueError, TypeError):
            return False
    return False


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


async def run_server(config: Any | None = None) -> None:
    """Run the TTS Unix socket server (command + audio)."""
    if config is None:
        config = global_config.tts

    logger.info("Starting minia_tts server...")

    cmd_path = Path(config.cmd_socket_path)
    cmd_path.parent.mkdir(parents=True, exist_ok=True)

    audio_path = Path(config.audio_socket_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    provider = await create_provider(config)

    playback = create_output(config.output_mode, provider.SAMPLE_RATE)
    if playback:
        playback.wait_for_ready()  # type: ignore[attr-defined]

    audio_clients: list = []

    state = TTSState(
        provider=provider,
        output_playback=playback,
        output_stream=None,
        command_queue=None,
        config=TTSConfig(
            voice=provider._voice_name,
            language=config.language,
            speed=config.speed,
            volume=config.volume,
            output_mode=config.output_mode,
        ),
    )

    def cmd_handler(r, w):
        return _handle_command_client(r, w, state, audio_clients)

    def audio_handler(r, w):
        return _handle_audio_client(r, w, audio_clients)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    try:
        await asyncio.gather(
            _run_socket_server(str(cmd_path), cmd_handler, stop),
            _run_socket_server(str(audio_path), audio_handler, stop),
            return_exceptions=True,
        )
    finally:
        provider.shutdown()
        if playback:
            playback.shutdown()


def main() -> None:
    """Entry point for the minia_tts server."""
    from minia_utils.logging import configure_logging, resolve_log_level

    configure_logging(
        log_level=resolve_log_level(global_config, "tts"),
        add_console=True,
    )
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
