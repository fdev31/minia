"""Async client that listens to the minia event socket."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


async def run_event_client(
    socket_path: str,
    on_message: Callable[[dict], Any],
    *,
    auto_reconnect: bool = True,
    max_reconnect_attempts: int = 0,
) -> None:
    """Connect to the minia event socket and relay messages.

    Parameters
    ----------
    socket_path :
        Path to the Unix socket.
    on_message :
        Callback called for each parsed JSON message.
    auto_reconnect :
        Whether to reconnect automatically on disconnect.
    max_reconnect_attempts :
        Maximum reconnect attempts (0 = infinite).
    """
    reconnect_count = 0
    stop = False

    while not stop:
        try:
            reader, writer = await asyncio.open_unix_connection(socket_path)
            reconnect_count = 0

            while True:
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

            if auto_reconnect and not stop:
                delay = min(2.0 * (2**reconnect_count), 30.0)
                reconnect_count += 1
                if max_reconnect_attempts and reconnect_count > max_reconnect_attempts:
                    logger.error(
                        "Max reconnect attempts (%d) reached for %s",
                        max_reconnect_attempts,
                        socket_path,
                    )
                    break
                logger.warning(
                    "Reconnecting to %s in %.1fs (attempt %d)...",
                    socket_path,
                    delay,
                    reconnect_count,
                )
                await asyncio.sleep(delay)

        except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
            if auto_reconnect and not stop:
                delay = min(2.0 * (2**reconnect_count), 30.0)
                reconnect_count += 1
                if max_reconnect_attempts and reconnect_count > max_reconnect_attempts:
                    logger.error(
                        "Max reconnect attempts (%d) reached for %s",
                        max_reconnect_attempts,
                        socket_path,
                    )
                    break
                logger.warning(
                    "Cannot connect to %s: %s. Retrying in %.1fs...",
                    socket_path,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise


async def _main_loop(socket_path: str) -> None:
    """Simple event loop for testing/standalone use."""

    def on_msg(msg: dict) -> None:
        logger.debug("[Audio] Received: %s", json.dumps(msg)[:200])

    await run_event_client(socket_path, on_msg)


if __name__ == "__main__":
    from minia_config import config

    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(_main_loop(config.default.event_socket_path))
