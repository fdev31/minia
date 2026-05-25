"""Command handling for the TTS service."""

from __future__ import annotations

import asyncio
import json
import logging
import struct

from minia_tts.kokoro.constants import KOKORO_VOICES, KOKORO_TO_ISO
from minia_tts.cancellation import CancellationToken
from minia_tts.protocol import (
    CMD_STATUS,
    CMD_STOP,
    CMD_TEXT,
    RES_STATUS,
    TTSCommand,
    TTSState,
    _send_error,
    _send_ok,
)
from minia_tts.synthesis import _speak_text
from minia_tts.preprocess import preprocess_text

logger = logging.getLogger(__name__)


async def read_command(reader) -> tuple[int, bytes] | None:
    """Read a complete command (byte + payload) atomically from the socket."""
    cmd_data = await reader.readexactly(1)
    if not cmd_data:
        return None
    cmd = cmd_data[0]

    if cmd == CMD_TEXT:
        len_data = await reader.readexactly(2)
        payload_len = struct.unpack("!H", len_data)[0]
        payload = await reader.readexactly(payload_len)
    elif cmd in (CMD_STOP, CMD_STATUS):
        payload = await reader.readexactly(2)
    else:
        try:
            payload = await reader.readexactly(2)
        except asyncio.IncompleteReadError:
            payload = b""

    return (cmd, payload)


async def handle_command(writer, reader, state: TTSState) -> None:
    """Handle a single command from the client (fallback for non-queue mode)."""
    cmd_data = await reader.readexactly(1)
    if not cmd_data:
        return
    cmd = cmd_data[0]

    if cmd == CMD_TEXT:
        len_data = await reader.readexactly(2)
        payload_len = struct.unpack("!H", len_data)[0]
        payload = await reader.readexactly(payload_len)
        text = payload.decode("utf-8")
        await _handle_text(writer, state, text)
    elif cmd == CMD_STOP:
        await reader.readexactly(2)
        await _handle_stop(writer, state)
    elif cmd == CMD_STATUS:
        await reader.readexactly(2)
        await _handle_status(writer, state)
    else:
        await _send_error(writer, f"Unknown command: 0x{cmd:02x}")


async def dispatch_command(
    writer, state: TTSState, cmd: int, payload: bytes, stop_writer=None, queue=None
) -> None:
    """Dispatch a pre-read command to the appropriate handler."""
    logger.info(
        "[TTS] dispatch_command: ENTER cmd=0x%02x payload_len=%d speaking=%s "
        "current_text='%s' output_playback=%s",
        cmd,
        len(payload),
        state.synthesis.speaking,
        state.synthesis.current_text[:50],
        state.output_playback is not None,
    )
    if cmd == CMD_TEXT:
        text = payload.decode("utf-8")
        await _handle_text(writer, state, text)
    elif cmd == CMD_STOP:
        await _handle_stop(
            writer, state, response_writer=stop_writer or writer, current_writer=writer
        )
        # Clear any remaining commands in the queue to prevent old text from playing
        if queue is not None:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except Exception:
                    break
    elif cmd == CMD_STATUS:
        await _handle_status(writer, state)
    else:
        await _send_error(writer, f"Unknown command: 0x{cmd:02x}")


async def _handle_text(writer, state: TTSState, text: str) -> None:
    """Handle TEXT command - synthesize and speak text."""
    stripped = text.strip()

    # Exact-match commands
    if stripped == TTSCommand.STOP:
        await _handle_stop(writer, state)
        return
    if stripped == TTSCommand.STATUS:
        await _handle_status(writer, state)
        return
    if stripped == TTSCommand.LIST_VOICES:
        voices = {}
        for voice in KOKORO_VOICES:
            lang_code = voice[0]
            gender = voice[1]
            lang = KOKORO_TO_ISO.get(lang_code, "unknown")
            voices[voice] = {"gender": gender, "language": lang}
        payload = json.dumps(voices).encode("utf-8")
        writer.write(struct.pack("!B", RES_STATUS))
        writer.write(struct.pack("!H", len(payload)))
        writer.write(payload)
        await writer.drain()
        return

    # Prefix commands with arguments
    for cmd in (
        TTSCommand.VOICE,
        TTSCommand.LANGUAGE,
        TTSCommand.SPEED,
        TTSCommand.VOLUME,
    ):
        prefix = cmd.prefix
        if text.startswith(prefix):
            arg = text[len(prefix) :].strip()
            match cmd:
                case TTSCommand.VOICE:
                    if arg in KOKORO_VOICES:
                        state.config.voice = arg
                        state.provider.set_voice(arg)
                        await _send_ok(writer)
                    else:
                        await _send_error(writer, f"Unknown voice: {arg}")
                case TTSCommand.LANGUAGE:
                    state.config.language = arg
                    state.provider.set_language(arg)
                    await _send_ok(writer)
                case TTSCommand.SPEED:
                    try:
                        speed = float(arg)
                        state.config.speed = speed
                        state.provider.set_speed(speed)
                        await _send_ok(writer)
                    except ValueError:
                        await _send_error(writer, "Invalid speed value")
                case TTSCommand.VOLUME:
                    try:
                        volume = float(arg)
                        state.config.volume = volume
                        state.provider.set_volume(volume)
                        await _send_ok(writer)
                    except ValueError:
                        await _send_error(writer, "Invalid volume value")
            return

    text = preprocess_text(text)
    await _speak_text(writer, state, text)


async def _handle_stop(
    writer, state: TTSState, response_writer=None, current_writer=None
) -> None:
    """Handle STOP command - interrupt current speech."""
    state.synthesis._cancellation.cancel()
    await state.provider.stop()
    state.provider._cancellation = CancellationToken()
    if state.output_playback:
        await state.output_playback.stop()
    state.synthesis.speaking = False
    state.synthesis.current_text = ""
    await _send_ok(writer)
    if response_writer is not None and response_writer is not writer:
        await _send_ok(response_writer)


async def _handle_status(writer, state: TTSState) -> None:
    """Handle STATUS command - return current status."""
    status = {
        "speaking": state.synthesis.speaking,
        "voice": state.config.voice,
        "language": state.config.language,
        "speed": state.config.speed,
        "volume": state.config.volume,
        "output_mode": state.config.output_mode,
        "current_text": state.synthesis.current_text,
    }
    payload = json.dumps(status).encode("utf-8")
    writer.write(struct.pack("!B", RES_STATUS))
    writer.write(struct.pack("!H", len(payload)))
    writer.write(payload)
    await writer.drain()
