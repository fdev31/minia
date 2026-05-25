#!/usr/bin/env -S mitmweb -q --mode upstream:http://gamix.lan:8080 -s
"""
decode_chat.py — Intercept & beautifully render LLM chat completions via mitmproxy.

Usage:
    mitmproxy -q --mode upstream:http://gamix.lan:8080 -s decode_chat.py

Or with the shebang:
    ./decode_chat.py

Intercepts POST /chat/completions and /v1/chat/completions, formats
streaming and non-streaming responses with rich panels, and displays
reasoning, tool calls, and token usage.
"""

import json

from mitmproxy import http
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _tool_panel(data: dict | str) -> Panel:
    """Render a tool call as a compact rich panel."""
    if isinstance(data, str):
        return Panel(
            escape(data),
            title="[bold cyan]🔧 Tool Call[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
    return Panel(
        f"[bold]ID:[/bold] {data.get('id', 'N/A')}\n"
        f"[bold]Function:[/bold] [bold yellow]{data.get('function', {}).get('name', 'N/A')}[/bold yellow]\n"
        f"[bold]Args:[/bold] {escape(data.get('function', {}).get('arguments', ''))}",
        title="[bold cyan]🔧 Tool Call[/bold cyan]",
        border_style="cyan",
        padding=(0, 1),
    )


def _banner(label: str, style: str = "bold white") -> Panel:
    """Render a compact banner."""
    return Panel(label, title="📨", border_style=style)


def _print_panel(content: str | dict, title: str, border: str) -> None:
    """Render a content panel with consistent padding."""
    if isinstance(content, dict):
        content = json.dumps(content, indent=2)
    console.print(
        Panel(escape(content), title=title, border_style=border, padding=(0, 1))
    )


# ── Stream State ─────────────────────────────────────────────────────────────


class StreamState:
    """Tracks all state for a single streaming response."""

    def __init__(self) -> None:
        self.content: str = ""
        self.reasoning: str = ""
        self.tool_calls: dict[int, dict] = {}


class StreamProcessor:
    """Accumulates SSE chunks until a stream completes, then emits formatted output."""

    def __init__(self) -> None:
        self._streams: dict[int, StreamState] = {}

    def process(self, flow: http.HTTPFlow, chunk_data: dict) -> tuple | None:
        """Process one SSE chunk. Returns (output_parts, usage) when complete, else None."""
        choices = chunk_data.get("choices")
        if not choices:
            return None

        choice = choices[0]
        idx = choice.get("index", 0)
        delta = choice.get("delta", {}) or {}
        finish = choice.get("finish_reason")

        # Bootstrap state for this stream
        if idx not in self._streams:
            self._streams[idx] = StreamState()

        state = self._streams[idx]

        # ── Reasoning (e.g. DeepSeek o1/o3-style) ──────────────────────────
        if (reason := delta.get("reasoning_content")) is not None:
            state.reasoning += reason or ""

        # ── Regular text content ────────────────────────────────────────────
        if (text := delta.get("content")) is not None:
            state.content += text or ""

        # ── Tool calls (function calling) ───────────────────────────────────
        for tc in delta.get("tool_calls") or []:
            tc_i = tc.get("index", 0)
            if tc_i not in state.tool_calls:
                state.tool_calls[tc_i] = {
                    "id": None,
                    "function": {"name": "", "arguments": ""},
                }
            entry = state.tool_calls[tc_i]
            if tc.get("id"):
                entry["id"] = tc["id"]
            if func := tc.get("function"):
                if func.get("name"):
                    entry["function"]["name"] = func["name"]
                if func.get("arguments"):
                    entry["function"]["arguments"] += func["arguments"]

        # ── Stream complete? Emit ───────────────────────────────────────────
        if not finish:
            return None

        # Collect parts in order: reasoning → content → tool calls
        parts: list[tuple[str, str | dict]] = []
        if state.reasoning:
            parts.append(("reasoning", state.reasoning))
        if state.content:
            parts.append(("content", state.content))
        for tc in state.tool_calls.values():
            parts.append(("tool_call", tc))

        usage = chunk_data.get("usage")
        self._streams.pop(idx, None)
        return parts, usage


# ── Output Rendering ─────────────────────────────────────────────────────────


def _print_output(parts: list[tuple[str, str | dict]], usage: dict | None) -> None:
    """Render accumulated output parts and optional token usage."""
    renderers = {
        "reasoning": ("💭 Reasoning", "dim"),
        "content": ("📝 Content", "green"),
    }
    for kind, data in parts:
        if kind == "tool_call":
            console.print(_tool_panel(data))
        elif kind in renderers:
            title, border = renderers[kind]
            _print_panel(data, f"[bold]{title}[/bold]", border)

    # Token usage table
    if usage:
        t = Table(
            title="[bold magenta]📊 Token Usage[/bold magenta]",
            title_style="magenta",
            border_style="magenta",
            expand=True,
        )
        t.add_column("Metric", style="cyan")
        t.add_column("Count", style="white", justify="right")
        t.add_row("Prompt tokens", str(usage.get("prompt_tokens", 0)))
        t.add_row("Completion tokens", str(usage.get("completion_tokens", 0)))
        t.add_row("Total tokens", str(usage.get("total_tokens", 0)))
        if (prompt := usage.get("prompt_tokens")) and (
            completion := usage.get("completion_tokens")
        ):
            t.add_row("Ratio", f"1:{completion / prompt:.2f}" if prompt else "N/A")
        console.print(t)


def format_conversation(
    messages: list[dict], model: str = "", response: str = ""
) -> None:
    """Render a conversation history with rich panels."""
    role_meta = {
        "system": ("⚙️  SYSTEM", "bold blue", "blue"),
        "user": ("👤  USER", "bold green", "green"),
        "assistant": ("🤖  ASSISTANT", "bold yellow", "yellow"),
        "tool": ("🔧  TOOL", "bold magenta", "magenta"),
    }

    def _render(msg: dict) -> None:
        role = msg.get("role", "unknown")
        emoji, style, border = role_meta.get(
            role, ("❓  UNKNOWN", "bold white", "white")
        )
        console.print(f"[dim]{emoji}[/dim]")
        content = msg.get("content") or ""
        if role == "tool":
            tcid = msg.get("tool_call_id", "")
            _print_panel(content, f"[dim]tool_call_id: {tcid}[/dim]", border)
        elif content:
            _print_panel(content, "", border)
        for tc in msg.get("tool_calls") or []:
            console.print(_tool_panel(tc))

    if model:
        console.print(f"[dim]Model: {model}[/dim]")
    for i, msg in enumerate(messages):
        _render(msg)
        if i < len(messages) - 1:
            console.print(Rule(style="dim"))

    if response:
        console.print(Rule(style="dim"))
        _render({"role": "assistant", "content": response})


# ── mitmproxy Hooks ──────────────────────────────────────────────────────────

proc = StreamProcessor()
EMDPOINTS = ("/chat/completions", "/v1/chat/completions")


def request(flow: http.HTTPFlow) -> None:
    """Intercept chat completion requests."""
    if flow.request.method != "POST":
        return
    if not any(flow.request.pretty_url.endswith(ep) for ep in EMDPOINTS):
        return
    if "application/json" not in flow.request.headers.get("Content-Type", ""):
        return

    try:
        data = json.loads(flow.request.get_text())
    except json.JSONDecodeError as e:
        console.print(f"[bold red]⚠️  Invalid JSON in request body: {e}[/bold red]")
        return

    messages = data.get("messages", [])
    if not messages:
        console.print("[bold yellow]⚠️  No messages in request[/bold yellow]")
        return

    model = data.get("model", "unknown")
    stream = data.get("stream", False)

    if not stream:
        console.print(_banner("REGULAR COMPLETION", "blue"))
        format_conversation(messages, model)
        console.print()
    else:
        flow.stream = True
        console.print(_banner(f"STREAMING — model: {model}", "green"))


def response(flow: http.HTTPFlow) -> None:
    """Process streaming SSE responses."""
    if not any(flow.request.pretty_url.endswith(ep) for ep in EMDPOINTS):
        return
    if not flow.stream:
        return
    if "text/event-stream" not in flow.response.headers.get("Content-Type", ""):
        return

    for raw in flow.response.text.split("\n\n"):
        raw = raw.strip()
        if not raw or raw == "[DONE]":
            continue

        try:
            if raw.startswith("data: "):
                raw = raw[6:]
            chunk = json.loads(raw)
        except json.JSONDecodeError:
            continue

        result = proc.process(flow, chunk)
        if result is not None:
            parts, usage = result
            _print_output(parts, usage)
            console.print()
