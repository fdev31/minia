"""Cooperative cancellation token for TTS synthesis."""

from __future__ import annotations

import threading


class CancellationToken:
    """Simple cooperative cancellation token.

    Propagates a stop signal through all layers of the synthesis pipeline.
    Thread-safe: ``cancel()`` and ``is_cancelled`` work correctly across
    event-loop and executor threads.
    """

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._done_event = threading.Event()

    def cancel(self) -> None:
        """Cancel the current operation."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def set_done(self) -> None:
        """Signal that synthesis has completed naturally."""
        self._done_event.set()

    def wait_for_done(self, timeout: float | None = None) -> bool:
        """Block until synthesis completes or timeout elapses.

        Returns True if done was signalled, False on timeout.
        """
        return self._done_event.wait(timeout=timeout)
