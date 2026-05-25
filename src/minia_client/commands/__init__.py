"""Command registry for slash commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable

from prompt_toolkit.completion import Completer


@dataclass
class SubCommand:
    description: str
    args: list[str] = field(default_factory=list)


@dataclass
class Command:
    name: str
    aliases: list[str]
    description: str
    handler: Callable | None = None
    usage: str = ""
    subcommands: dict[str, SubCommand] = field(default_factory=dict)
    completer: Completer | None = None


class CommandRegistry:
    """Registry for slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._commands[alias] = cmd

    def lookup(self, name: str) -> Command | None:
        return self._commands.get(name)

    def list_commands(self) -> list[Command]:
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return result

    def get_completer(self) -> Completer | None:
        for cmd in self._commands.values():
            if cmd.completer is not None:
                return cmd.completer
        return None
