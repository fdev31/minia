from __future__ import annotations

import json

from typing import Any

from mcp.client.session_group import (  # type: ignore[import-not-found]
    ClientSessionGroup,
    SseServerParameters,
    StdioServerParameters,
    StreamableHttpParameters,
)
from mcp.types import TextContent  # type: ignore[import-not-found]

from minia_utils.logging import get_logger
from minia_llm.serialization import ToolResult, serialize
from minia_config import config

logger = get_logger(__name__)


def _convert_tool_to_openai(mcp_tool) -> dict:
    """Convert an MCP Tool to an OpenAI-compatible function schema."""
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description or "",
            "parameters": {
                "type": "object",
                "properties": mcp_tool.inputSchema.get("properties", {}),
                "required": mcp_tool.inputSchema.get("required", []),
            },
        },
    }


def _format_tool_result(result, tool_name: str | None = None) -> str:
    """Format a CallToolResult using the configured serialization format.

    The structured format gives the LLM explicit signals about success/failure
    and content boundaries, reducing tool call loops caused by ambiguous results.
    """
    parts = []
    for content in result.content:
        if isinstance(content, TextContent):
            parts.append(content.text)
        else:
            parts.append(json.dumps(content.model_dump(), default=str))
    content_text = "\n\n".join(parts)

    status = "error" if result.isError else "success"
    tool_result = ToolResult(
        status=status, content=content_text, tool_name=tool_name or ""
    )
    return serialize(tool_result, config.llm.tool_format)


class McpClient:
    """MCP client that connects to an MCP server and discovers tools/prompts."""

    def __init__(
        self,
        transport: str | None = None,
        server_url: str | None = None,
        server_command: list[str] | None = None,
        server_env: dict[str, str] | None = None,
        server_cwd: str | None = None,
        server_id: str = "",
    ):
        self.transport = transport
        self.server_url = server_url
        self.server_command = server_command
        self.server_env = server_env
        self.server_cwd = server_cwd
        self.server_id = server_id
        self._group: Any | None = None
        self._session: Any = None
        self._mcp_tools: list = []
        self._mcp_prompts: list = []
        self._tool_schemas_by_name: dict[str, dict] = {}

    @property
    def tool_descriptions(self) -> list[tuple[str, str]]:
        """Return (name, description) pairs for the Manager's system prompt."""
        return [(t.name, t.description or "") for t in self._mcp_tools]

    @property
    def tool_schemas(self) -> list[dict]:
        """Return full OpenAI-compatible tool schemas for the Worker Agent."""
        return [_convert_tool_to_openai(t) for t in self._mcp_tools]

    def get_tool_schema(self, name: str) -> dict | None:
        """Return the full schema for a tool by name, or None if not found."""
        return self._tool_schemas_by_name.get(name)

    @property
    def prompt_descriptions(self) -> list[tuple[str, str]]:
        """Return (name, description) pairs for discovered prompts."""
        return [(p.name, p.description or "") for p in self._mcp_prompts]

    async def __aenter__(self) -> McpClient:
        await self._connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self._close()

    async def _connect(self) -> None:
        logger.debug(
            "[MCP] Connecting | server=%s | transport=%s | command=%s | cwd=%s | env_keys=%s",
            self.server_id,
            self.transport,
            self.server_command,
            self.server_cwd,
            list(self.server_env.keys()) if self.server_env else "inherited",
        )
        self._group = ClientSessionGroup()
        await self._group.__aenter__()

        server_params = self._build_server_params()
        self._session = await self._group.connect_to_server(server_params)

        # Tools and prompts are cached automatically by ClientSessionGroup
        self._mcp_tools = list(self._group.tools.values())
        self._mcp_prompts = list(self._group.prompts.values())
        self._tool_schemas_by_name = {
            t.name: _convert_tool_to_openai(t) for t in self._mcp_tools
        }
        logger.info(
            "[MCP] Connected | server=%s | tools=%d | prompts=%d",
            self.server_id,
            len(self._mcp_tools),
            len(self._mcp_prompts),
        )
        for tool in self._mcp_tools:
            logger.debug(f"  **{tool.name}**: {tool.description}")

    async def _close(self) -> None:
        if self._group:
            await self._group.__aexit__(None, None, None)
            self._group = None
            self._session = None

    def _build_server_params(self):
        if self.transport == "stdio":
            assert self.server_command
            return StdioServerParameters(
                command=self.server_command[0],
                args=self.server_command[1:],
                env=self.server_env,
                cwd=self.server_cwd,
            )
        elif self.transport == "sse":
            assert self.server_url
            return SseServerParameters(url=self.server_url)
        elif self.transport == "streamable-http":
            assert self.server_url
            return StreamableHttpParameters(url=self.server_url)
        else:
            raise ValueError(f"Unknown transport: {self.transport}")

    async def call_tool(
        self, name: str, args: dict | None = None, tool_name: str | None = None
    ) -> str:
        """Call an MCP tool and return the formatted result."""
        if not self._group:
            raise RuntimeError(
                "MCP client is not connected. Use 'async with' or call __aenter__ first."
            )
        logger.debug(
            "[MCP] call_tool | server=%s | tool=%s | args=%s",
            self.server_id,
            name,
            json.dumps(args) if args else "None",
        )
        result = await self._group.call_tool(name, args)
        formatted = _format_tool_result(result, tool_name=tool_name)
        logger.debug(
            "[MCP] result | server=%s | tool=%s | error=%s | len=%d | preview=%s",
            self.server_id,
            name,
            result.isError,
            len(formatted),
            formatted[:200],
        )
        return formatted

    async def get_prompt(self, name: str, arguments: dict | None = None) -> str:
        """Fetch an MCP prompt and return its formatted content."""
        if not self._group:
            raise RuntimeError(
                "MCP client is not connected. Use 'async with' or call __aenter__ first."
            )
        logger.debug(
            "[MCP] get_prompt | server=%s | prompt=%s | args=%s",
            self.server_id,
            name,
            json.dumps(arguments) if arguments else "None",
        )
        result = await self._group.prompts[name].get(arguments)
        parts = []
        for msg in result.messages:
            parts.append(msg.content.text)
        text = "\n\n".join(parts)
        logger.debug(
            "[MCP] prompt_result | server=%s | prompt=%s | len=%d | preview=%s",
            self.server_id,
            name,
            len(text),
            text[:200],
        )
        return text
