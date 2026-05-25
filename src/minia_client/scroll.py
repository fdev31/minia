"""Scroll management for ChatUI output pane.

Handles the ``[SetCursorPosition]`` marker used by prompt_toolkit's
FormattedTextControl to control scroll position.
"""

from __future__ import annotations

from typing import Any


def fragments_with_cursor(
    fragments: list[tuple[str, str]],
    cursor_offset: int,
) -> list[tuple[str, Any]]:
    """Return fragments with a ``[SetCursorPosition]`` marker for scroll control.

    When ``cursor_offset`` is 0, the marker is at the end (auto-scroll mode).
    When manually scrolled, the marker is placed ``cursor_offset`` newlines
    up from the end.

    Args:
        fragments: Current fragment list.
        cursor_offset: Lines up from bottom (0 = at bottom / auto-scroll).

    Returns:
        Fragment list with cursor marker inserted at the right position.
    """
    if not fragments or cursor_offset == 0:
        result: list[tuple[str, Any]] = list(fragments)
        result.append(("[SetCursorPosition]", ""))
        return result

    newlines_seen = 0
    for i in range(len(fragments) - 1, -1, -1):
        text = fragments[i][1]
        for ch in reversed(text):
            if ch == "\n":
                newlines_seen += 1
                if newlines_seen >= cursor_offset:
                    result = list(fragments[: i + 1])
                    result.append(("[SetCursorPosition]", ""))
                    result.extend(fragments[i + 1 :])
                    return result
    result = [("SetCursorPosition", "")]
    result.extend(fragments)
    return result
