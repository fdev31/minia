"""Stream raw PCM audio bytes back over the socket to the client."""

from __future__ import annotations

import logging
import struct
from typing import Any

import numpy as np


from minia_sockets.server import SOCKET_DISCONNECT_ERRORS
from minia_tts.output.base import AudioOutput

logger = logging.getLogger(__name__)


class StreamOutput(AudioOutput):
    """Streams raw PCM audio bytes back over a socket writer."""

    # Frame size for float32 PCM
    FRAME_SIZE = 4  # 4 bytes per float32 sample

    def __init__(self, writer: Any) -> None:
        self._writer = writer
        self._playing = False

    async def play(self, audio: np.ndarray, sample_rate: int) -> None:
        """Stream audio chunks to the client over the socket."""
        if len(audio) == 0:
            return
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        try:
            self._writer.write(
                struct.pack("!I", len(audio_int16)) + audio_int16.tobytes()
            )
            await self._writer.drain()
            self._playing = True
        except SOCKET_DISCONNECT_ERRORS as e:
            logger.error("Stream output write error: %s", e)
            self._playing = False

    async def stop(self) -> None:
        """Stop streaming immediately."""
        self._playing = False

    def is_playing(self) -> bool:
        """True if currently streaming audio."""
        return self._playing

    def shutdown(self) -> None:
        """Release resources."""
        self._playing = False
