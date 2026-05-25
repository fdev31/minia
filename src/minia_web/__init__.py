"""minia_web — Web interface for MinIA assistant.

A hybrid of minia_chatloop and minia_client that exposes the assistant
via a web interface with message sending, response viewing, and audio playback.
"""

from minia_web.server import main

__all__ = ["main"]
