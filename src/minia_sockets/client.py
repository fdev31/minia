"""Simple Unix socket connection helper."""

from __future__ import annotations

import asyncio


async def connect_unix(path: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to a Unix socket and return (reader, writer)."""
    return await asyncio.open_unix_connection(path)
