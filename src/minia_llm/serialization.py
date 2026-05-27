"""Serialization module for tool results.

Provides a unified interface for serializing tool results into
different formats (yaml, xml, json) for consumption by LLM agents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Structured representation of a tool call result."""

    status: str  # "success" | "error"
    content: str
    tool_name: str = ""
    truncated: bool = False


def serialize(result: ToolResult, fmt: str = "yaml") -> str:
    """Serialize a ToolResult to the given format.

    Args:
        result: The tool result to serialize.
        fmt: Output format - "yaml" (default), "xml", or "json".

    Returns:
        The serialized string.
    """
    fmt = fmt.lower()
    if fmt == "yaml":
        return _to_yaml(result)
    elif fmt == "xml":
        return _to_xml(result)
    elif fmt == "json":
        return _to_json(result)
    else:
        raise ValueError(f"Unsupported format: {fmt}. Use 'yaml', 'xml', or 'json'.")


def _to_yaml(result: ToolResult) -> str:
    """Serialize to YAML format."""
    lines = [f"status: {result.status}"]
    if result.tool_name:
        lines.append(f"tool_name: {result.tool_name}")
    if result.truncated:
        lines.append("truncated: true")
    # Use literal block scalar for content to preserve newlines
    content = result.content
    if "\n" in content:
        lines.append("content: |")
        for line in content.splitlines():
            lines.append(f"  {line}")
    else:
        lines.append(f"content: {content}")
    return "\n".join(lines)


def _to_xml(result: ToolResult) -> str:
    """Serialize to XML format."""
    parts = ["<tool_result>"]
    parts.append(f"<status>{result.status}</status>")
    if result.tool_name:
        parts.append(f"<tool_name>{result.tool_name}</tool_name>")
    if result.truncated:
        parts.append("<truncated>true</truncated>")
    parts.append(f"<content>{_xml_escape(result.content)}</content>")
    parts.append("</tool_result>")
    return "\n".join(parts)


def _to_json(result: ToolResult) -> str:
    """Serialize to JSON format."""
    data = {
        "status": result.status,
        "content": result.content,
    }
    if result.tool_name:
        data["tool_name"] = result.tool_name
    if result.truncated:
        data["truncated"] = "yes"
    return json.dumps(data)


def _xml_escape(text: str) -> str:
    """Escape special XML characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
