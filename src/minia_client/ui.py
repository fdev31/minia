"""ChatUI — full-screen chat interface built on prompt_toolkit.

Layout::

    ┌─────────────────────────────────────┐
    │  (scrollable output)                │
    │  You: hello                         │
    │  LLM: Hi! How can I help?           │
    ├─────────────────────────────────────┤
    │ LLM> _                              │
    └─────────────────────────────────────┘

The output pane uses ``FormattedTextControl`` backed by a mutable
fragment list so we can append styled text from background tasks
and call ``app.invalidate()`` to trigger a re-render.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from minia_client.logger import logger
from typing import Any

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from minia_client.completion import SlashCompleter
from minia_client.markdown import format_tokens, markdown_to_fragments
from minia_client.scroll import fragments_with_cursor


# ---------------------------------------------------------------------------
# Style names
# ---------------------------------------------------------------------------

_S_USER = "class:user"
_S_USER_LABEL = "class:user-label"
_S_LLM = "class:llm"
_S_LLM_LABEL = "class:llm-label"
_S_LLM_STREAM = "class:llm-stream"
_S_TOOL = "class:tool"
_S_EVENT = "class:event"
_S_ERROR = "class:error"
_S_THINKING = "class:thinking"
_S_SEPARATOR = "class:separator"
_S_DIM = "class:dim"

_S_TOKEN_COUNT = "class:token-count"
_STYLE = Style.from_dict(
    {
        "user": "#00aaff",
        "user-label": "#00aaff bold",
        "llm": "#44cc44",
        "llm-label": "#44cc44 bold",
        "llm-stream": "#44cc44",
        "tool": "#cc77ff",
        "event": "#cccc44",
        "error": "#ff4444 bold",
        "thinking": "#888888 italic",
        "md-heading": "#44cc44 bold",
        "md-bold": "bold",
        "md-bold italic": "bold italic",
        "md-italic": "italic",
        "md-code": "#ffaa44",
        "md-code-block": "#ffaa44",
        "md-bullet": "#888888",
        "md-text": "",
        "separator": "#555555",
        "dim": "#888888",
        "token-count": "#666666",
    }
)

# ---------------------------------------------------------------------------
# Chat UI
# ---------------------------------------------------------------------------


class ChatUI:
    """Full-screen chat interface.

    Provides methods to append styled content to the output pane from
    any coroutine, and an input field with slash-command completion.
    """

    def __init__(
        self,
        on_submit: Callable[[str], Any],
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_exit = on_exit
        self._on_skip_sentence: Callable | None = None
        self._fragments: list[tuple[str, str]] = []

        # Track streaming state so we can replace raw tokens with
        # rendered markdown when the response is complete.
        self._stream_start: int | None = None
        self._stream_buffer: str = ""

        # Scroll state
        self._auto_scroll: bool = True
        self._cursor_offset: int = 0

        # --- Output pane ---
        self._output_control = FormattedTextControl(
            text=self._output_text,
            focusable=True,
            show_cursor=False,
        )
        self._output_window = Window(
            content=self._output_control,
            wrap_lines=True,
        )

        # --- Input field ---
        self._input_field = TextArea(
            height=1,
            prompt="LLM> ",
            multiline=False,
            dont_extend_height=True,
            completer=SlashCompleter(),
        )
        self._input_field.buffer.accept_handler = self._handle_accept

        # --- Token counter (right side of input row) ---
        self._token_fragments: list[tuple[str, str]] = []
        self._token_control = FormattedTextControl(
            text=lambda: self._token_fragments,
        )
        self._token_window = Window(
            content=self._token_control,
            width=D(min=8, max=18),
            height=1,
            dont_extend_width=True,
        )

        # --- Key bindings ---
        kb = self._build_keybindings()

        # --- Layout ---
        separator = Window(height=1, char="─", style=_S_SEPARATOR)
        input_row = VSplit([self._input_field, self._token_window])
        root = HSplit(
            [
                self._output_window,
                separator,
                input_row,
            ]
        )

        self.app: Application[None] = Application(
            layout=Layout(root, focused_element=self._input_field),
            key_bindings=kb,
            style=_STYLE,
            full_screen=True,
            mouse_support=True,
        )

    # ------------------------------------------------------------------
    # Output text callback (uses scroll management)
    # ------------------------------------------------------------------

    def _output_text(self) -> list[tuple[str, Any]]:
        """Return fragments with cursor marker for scroll control."""
        v: list[tuple[str, Any]] = fragments_with_cursor(
            self._fragments, self._cursor_offset
        )
        return v

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        def _exit(event: Any) -> None:
            if self._on_exit:
                self._on_exit()
            event.app.exit()

        @kb.add("c-o")
        def _toggle_focus(event: Any) -> None:
            layout = event.app.layout
            if layout.has_focus(self._input_field):
                layout.focus(self._output_window)
            else:
                layout.focus(self._input_field)

        @kb.add("escape")
        def _focus_input(event: Any) -> None:
            if self._on_skip_sentence:
                self._on_skip_sentence()
            event.app.layout.focus(self._input_field)

        @kb.add("c-up")
        def _scroll_output_up(event: Any) -> None:
            max_off = sum(t.count("\n") for _, t in self._fragments)
            if self._cursor_offset == 0:
                self._cursor_offset = min(max_off, event.app.output.get_size().rows + 1)
            else:
                self._cursor_offset = min(self._cursor_offset + 1, max_off)
            self._auto_scroll = False

        @kb.add("c-down")
        def _scroll_output_down(event: Any) -> None:
            max_off = sum(t.count("\n") for _, t in self._fragments)
            if self._cursor_offset == max_off:
                self._cursor_offset = max(
                    0, max_off - event.app.output.get_size().rows - 1
                )
            else:
                self._cursor_offset = max(0, self._cursor_offset - 1)
            if self._cursor_offset == 0:
                self._auto_scroll = True

        @kb.add("pageup")
        def _scroll_output_page_up(event: Any) -> None:
            max_off = sum(t.count("\n") for _, t in self._fragments)
            self._cursor_offset = min(
                self._cursor_offset + event.app.output.get_size().rows + 1, max_off
            )
            self._auto_scroll = False

        @kb.add("pagedown")
        def _scroll_output_page_down(event: Any) -> None:
            rows = event.app.output.get_size().rows
            self._cursor_offset = max(0, self._cursor_offset - rows)
            if self._cursor_offset == 0:
                self._auto_scroll = True

        @kb.add("c-end")
        def _scroll_to_bottom(event: Any) -> None:
            self._cursor_offset = 0
            self._auto_scroll = True

        @kb.add("c-home")
        def _scroll_to_top(event: Any) -> None:
            self._cursor_offset = sum(t.count("\n") for _, t in self._fragments)
            self._auto_scroll = False

        return kb

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _handle_accept(self, buff: Buffer) -> bool:
        """Called when the user presses Enter in the input field."""
        text = buff.text.strip()
        self._auto_scroll = True
        self._cursor_offset = 0
        if self._loop and asyncio.iscoroutinefunction(self._on_submit):
            self._loop.create_task(self._on_submit(text))
        else:
            self._on_submit(text)
        return False

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for async submit handling."""
        self._loop = loop

    @property
    def input_field(self) -> TextArea:
        return self._input_field

    def set_token_count(self, used: int, total: int) -> None:
        """Update the token counter display (right side of input row)."""
        self._token_fragments = [
            (_S_TOKEN_COUNT, f"~{format_tokens(used)} / {format_tokens(total)}"),
        ]
        self.app.invalidate()

    def focus_input(self) -> None:
        """Move focus to the input field."""
        with contextlib.suppress(Exception):
            self.app.layout.focus(self._input_field)

    # ------------------------------------------------------------------
    # Output: appending styled content
    # ------------------------------------------------------------------

    def _invalidate(self) -> None:
        """Schedule a re-render (auto-scrolls via cursor marker)."""
        try:
            app = get_app()
            app.invalidate()
        except Exception:
            logger.info(
                "UI invalidation failed (get_app may not have found the application context)",
                exc_info=True,
            )

    def append_user(self, text: str) -> None:
        """Show a user message in the output pane."""
        self._fragments.append((_S_USER_LABEL, "You: "))
        self._fragments.append((_S_USER, text))
        self._fragments.append(("", "\n"))
        self._invalidate()

    def begin_llm_response(self) -> None:
        """Mark the start of a new LLM streaming response."""
        self._fragments.append((_S_LLM_LABEL, "LLM: "))
        self._stream_start = len(self._fragments)
        self._stream_buffer = ""

    def append_llm_token(self, token: str) -> None:
        """Append a streamed token with progressive markdown rendering.

        Accumulates tokens in a buffer. On each token, the entire
        buffer is re-parsed as markdown and the fragments from
        ``_stream_start`` are replaced with the rendered result.
        """
        if self._stream_start is None:
            self.begin_llm_response()
        self._stream_buffer += token
        if self._stream_start is not None:
            del self._fragments[self._stream_start :]
            md_frags = markdown_to_fragments(self._stream_buffer, _S_LLM)
            self._fragments.extend(md_frags)
        self._invalidate()

    def append_thinking(self, token: str) -> None:
        """Append thinking/reasoning content (shown as dim italic text)."""
        self._fragments.append((_S_THINKING, token))
        self._invalidate()

    def finalize_llm_response(self, full_text: str) -> None:
        """Replace the streamed fragments with final rendered markdown."""
        if self._stream_start is not None:
            del self._fragments[self._stream_start :]
            md_frags = markdown_to_fragments(full_text.rstrip(), _S_LLM)
            self._fragments.extend(md_frags)
            self._stream_start = None
            self._stream_buffer = ""
        else:
            md_frags = markdown_to_fragments(full_text.rstrip(), _S_LLM)
            self._fragments.append((_S_LLM_LABEL, "LLM: "))
            self._fragments.extend(md_frags)

        if self._fragments and self._fragments[-1][1] != "\n":
            self._fragments.append(("", "\n"))
        self._invalidate()

    def cancel_llm_response(self) -> None:
        """Reset streaming state without replacing fragments."""
        self._fragments.append(("", "\n"))
        self._stream_start = None
        self._stream_buffer = ""

    def append_tool(self, text: str) -> None:
        """Show a tool call/result in the output pane."""
        self._fragments.append((_S_TOOL, f"[tool] {text}"))
        self._fragments.append(("", "\n"))
        self._invalidate()

    def append_event(self, text: str) -> None:
        """Show a system event or informational message."""
        self._fragments.append((_S_EVENT, text))
        self._fragments.append(("", "\n"))
        self._invalidate()

    def append_error(self, text: str) -> None:
        """Show an error message."""
        self._fragments.append((_S_ERROR, f"Error: {text}"))
        self._fragments.append(("", "\n"))
        self._invalidate()

    def append_dim(self, text: str) -> None:
        """Show dimmed text (status, hints)."""
        self._fragments.append((_S_DIM, text))
        self._fragments.append(("", "\n"))
        self._invalidate()

    def append_raw(self, style: str, text: str) -> None:
        """Append arbitrary styled text."""
        self._fragments.append((style, text))
        self._invalidate()

    def append_newline(self) -> None:
        """Append a blank line."""
        self._fragments.append(("", "\n"))
        self._invalidate()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run_async(self) -> None:
        """Start the full-screen application."""
        await self.app.run_async()
