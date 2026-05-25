"""Slash command tab completion for minia_client."""

from __future__ import annotations

from collections.abc import Generator

from prompt_toolkit.completion import Completer, Completion, CompleteEvent
from prompt_toolkit.document import Document

# Available slash commands: (name, aliases, description)
_SLASH_COMMANDS: list[tuple[str, list[str], str]] = [
    ("/help", ["-h"], "Show available commands"),
    ("/clear", ["-c"], "Clear conversation history"),
    ("/compact", [], "Compact conversation context"),
    ("/status", [], "Show connection status"),
    ("/exit", ["-e", "quit", "q"], "Exit the client"),
]


class SlashCompleter(Completer):
    """Tab completion for slash commands."""

    def get_completions(
        self, document: Document, event: CompleteEvent
    ) -> Generator[Completion, None, None]:
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        word_start = text.rfind(" ")
        word = text[word_start + 1 :] if word_start >= 0 else text

        if not word or word == "/":
            for name, aliases, desc in _SLASH_COMMANDS:
                yield Completion(
                    name, start_position=-len(word), display=f"{name}  {desc}"
                )
            return

        word_lower = word.lower().lstrip("/")
        for name, aliases, desc in _SLASH_COMMANDS:
            if name[1:].lower() == word_lower:
                yield Completion(
                    name, start_position=-len(word), display=f"{name}  {desc}"
                )
                return
            for alias in aliases:
                if alias.lower() == word_lower:
                    yield Completion(
                        name, start_position=-len(word), display=f"{name}  {desc}"
                    )
                    return
            if name[1:].lower().startswith(word_lower):
                yield Completion(
                    name, start_position=-len(word), display=f"{name}  {desc}"
                )
                return
