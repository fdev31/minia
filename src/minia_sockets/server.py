"""Shared Unix socket helpers for the minia project."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

SOCKET_DISCONNECT_ERRORS: tuple[type[Exception], ...] = (
    ConnectionResetError,
    BrokenPipeError,
    OSError,
)


@asynccontextmanager
async def open_unix(path: str):
    """Open a Unix socket connection and close it on exit."""
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        yield (reader, writer)
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def send_fire_and_forget(path: str, msg: dict) -> None:
    """Send a JSON-lines message to a Unix socket and close the connection."""
    async with open_unix(path) as (reader, writer):
        writer.write((json.dumps(msg) + "\n").encode())
        await writer.drain()
