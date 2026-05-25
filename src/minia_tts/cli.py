#!/usr/bin/env python3
"""CLI client for the minia_tts command socket.

Usage examples:
    minia-tts-client "Hello world"
    minia-tts-client --stop
    minia-tts-client --status
    minia-tts-client --list-voices
    minia-tts-client --set-voice af_bella "Hello"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from minia_config import config
from minia_protocol import tts_synthesize, tts_stop, tts_settings


async def _open_cmd_socket(path: str):
    """Open a connection to the TTS command socket."""
    reader, writer = await asyncio.open_unix_connection(path)
    return reader, writer


async def _main(args: argparse.Namespace) -> None:
    path = args.socket

    # --- Actions that need responses ---
    if args.list_voices:
        reader, writer = await _open_cmd_socket(path)
        writer.write((json.dumps({"type": "list_voices"}) + "\n").encode())
        await writer.drain()
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line:
                resp = json.loads(line)
                for name, info in sorted(resp.get("data", {}).items()):
                    lang = info.get("language", "?")
                    gender = info.get("gender", "?")
                    short_name = name[3:] if len(name) > 3 else name
                    print(f"  {short_name:<20} {lang:>4}  {gender}")
        except asyncio.TimeoutError:
            print("Timeout waiting for response", file=sys.stderr)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        return

    if args.status:
        reader, writer = await _open_cmd_socket(path)
        writer.write((json.dumps({"type": "status"}) + "\n").encode())
        await writer.drain()
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line:
                resp = json.loads(line)
                print(json.dumps(resp.get("data", {}), indent=2))
        except asyncio.TimeoutError:
            print("Timeout waiting for response", file=sys.stderr)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        return

    # --- Apply settings ---
    if args.set_voice:
        reader, writer = await _open_cmd_socket(path)
        writer.write(
            (json.dumps(tts_settings("voice", args.set_voice)) + "\n").encode()
        )
        await writer.drain()
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line:
                resp = json.loads(line)
                if resp.get("ok"):
                    print(f"Voice set to {args.set_voice}")
                else:
                    print(f"Invalid voice: {args.set_voice}", file=sys.stderr)
        except asyncio.TimeoutError:
            print("Timeout waiting for response", file=sys.stderr)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        return

    if args.set_language:
        reader, writer = await _open_cmd_socket(path)
        writer.write(
            (json.dumps(tts_settings("language", args.set_language)) + "\n").encode()
        )
        await writer.drain()
        print(f"Language set to {args.set_language}")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return

    if args.set_speed is not None:
        reader, writer = await _open_cmd_socket(path)
        writer.write(
            (json.dumps(tts_settings("speed", args.set_speed)) + "\n").encode()
        )
        await writer.drain()
        print(f"Speed set to {args.set_speed}")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return

    if args.set_volume is not None:
        reader, writer = await _open_cmd_socket(path)
        writer.write(
            (json.dumps(tts_settings("volume", args.set_volume)) + "\n").encode()
        )
        await writer.drain()
        print(f"Volume set to {args.set_volume}")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return

    # --- Stop ---
    if args.stop:
        reader, writer = await _open_cmd_socket(path)
        writer.write((json.dumps(tts_stop()) + "\n").encode())
        await writer.drain()
        print("Stopped.")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return

    # --- Speak text ---
    text = args.text.strip()
    if not text:
        print(
            "Error: no text provided. Use --list-voices or --status for info.",
            file=sys.stderr,
        )
        sys.exit(1)

    reader, writer = await _open_cmd_socket(path)
    writer.write((json.dumps(tts_synthesize(text)) + "\n").encode())
    await writer.drain()
    print("Synthesizing...")
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TTS client for the minia_tts server.",
    )
    parser.add_argument(
        "text",
        nargs="?",
        default="",
        help="Text to synthesize.",
    )
    parser.add_argument(
        "--socket",
        default=config.tts.cmd_socket_path,
        help="Path to the TTS command socket (default: %(default)s).",
    )
    parser.add_argument(
        "--set-voice",
        help="Set voice name (e.g. af_bella).",
    )
    parser.add_argument(
        "--set-language",
        help="Set language code (e.g. en, fr, es).",
    )
    parser.add_argument(
        "--set-speed",
        type=float,
        help="Set speech rate (0.5-2.0).",
    )
    parser.add_argument(
        "--set-volume",
        type=float,
        help="Set volume (0.0-2.0).",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List all available voices.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current server status.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop current speech.",
    )
    return parser.parse_args()


def main() -> None:
    from minia_utils.logging import configure_logging, resolve_log_level

    configure_logging(
        log_level=resolve_log_level(config, "tts"),
        add_console=True,
    )
    args = _parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
