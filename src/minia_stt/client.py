"""Socket client for sending recognized speech to minia."""

from __future__ import annotations

import asyncio
import json
import logging

from minia_protocol import cmd_input

logger = logging.getLogger(__name__)


class STTClient:
    """Fire-and-forget client that sends recognized speech to the minia command socket."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path

    async def send_text(self, text: str) -> None:
        """Send recognized text to the minia server (fire-and-forget)."""
        logger.debug("[STT] Sending: '%s'", text[:100])
        reader, writer = await asyncio.open_unix_connection(self._socket_path)
        writer.write((json.dumps(cmd_input(text)) + "\n").encode())
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
