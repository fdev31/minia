"""Shared utility functions for agent creation, tooling, and prompt building."""

from __future__ import annotations

import json
from typing import Awaitable, Callable

from .agent import Agent
from minia_mcp_client import McpClient
from minia_mcp_client.tool_schemas import (
    LOAD_TOOL_SCHEMA,
    build_delegate_task_schema,
    build_direct_tool_schemas,
)
from .model import LlmContext
from minia_utils.logging import get_logger

logger = get_logger(__name__)


def build_tool_executor(
    ctx: LlmContext, all_clients: dict[str, McpClient]
) -> Callable[[str, dict], Awaitable[str]]:
    """Build a shared tool executor with load_tool support and prefix-based routing.

    All agents (manager and workers) use this executor. It handles:
    - load_tool: parses server:tool prefix, gets schema from correct server
    - Auto-unfold: if a tool isn't in unfolded_tools, parses prefix to get schema
    - Routing: splits on ':' to find the correct server
    """

    async def executor(func_name: str, args: dict) -> str:
        if func_name == "load_tool":
            tool_name = args.get("tool_name", "")
            if ":" in tool_name:
                server_id, orig_name = tool_name.split(":", 1)
                client = all_clients.get(server_id)
                if client is not None:
                    schema = client.get_tool_schema(orig_name)
                    if schema is not None:
                        schema = dict(schema)
                        schema["function"] = dict(schema["function"])
                        schema["function"]["name"] = tool_name
                        ctx.unfolded_tools[tool_name] = schema
                        logger.info(
                            "[Agent] Tool unfolded: %s | server=%s",
                            tool_name,
                            server_id,
                        )
                        return json.dumps({"tool_name": tool_name, "schema": schema})
            available = ", ".join(
                f"{sid}:{name}"
                for sid, client in all_clients.items()
                for name, _ in client.tool_descriptions
            )
            return f"Error: Unknown tool '{tool_name}'. Available tools: {available}"

        if func_name not in ctx.unfolded_tools:
            if ":" in func_name:
                server_id, orig_name = func_name.split(":", 1)
                client = all_clients.get(server_id)
                if client is not None:
                    schema = client.get_tool_schema(orig_name)
                    if schema is not None:
                        ctx.unfolded_tools[func_name] = schema

        if ":" in func_name:
            server_id, orig_name = func_name.split(":", 1)
            client = all_clients.get(server_id)
            if client is not None:
                return await client.call_tool(orig_name, args, tool_name=func_name)

        raise RuntimeError(f"Unknown tool: {func_name}")

    return executor


def _matches_patterns(name: str, patterns: list[str]) -> bool:
    """Check if a tool name matches any of the given patterns.

    Patterns are matched against the full 'server:tool_name' string.
    Uses simple substring matching: a pattern matches if it appears
    anywhere in the tool name.
    """
    for pattern in patterns:
        if pattern in name:
            return True
    return False


def build_worker_tools_schema(
    all_clients: list[McpClient],
    whitelist: list[str] | None = None,
    blacklist: list[str] | None = None,
) -> list[dict]:
    """Build tool schemas for a worker agent, filtered by whitelist/blacklist.

    Filters match against the full 'server:tool_name' name.
    Empty whitelist means no restriction. Empty blacklist means no exclusion.
    Always includes LOAD_TOOL_SCHEMA.
    """
    tools: list[dict] = [LOAD_TOOL_SCHEMA]

    for client in all_clients:
        for name, desc in client.tool_descriptions:
            full_name = f"{client.server_id}:{name}"

            if whitelist and not _matches_patterns(full_name, whitelist):
                continue
            if blacklist and _matches_patterns(full_name, blacklist):
                continue

            schema = client.get_tool_schema(name)
            if schema is None:
                continue

            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": full_name,
                        "description": schema["function"]["description"],
                        "parameters": {
                            "type": "object",
                            "properties": schema["function"]
                            .get("parameters", {})
                            .get("properties", {}),
                            "required": schema["function"]
                            .get("parameters", {})
                            .get("required", []),
                        },
                    },
                }
            )

    return tools


def build_manager_tools_schema(
    mcp_clients: list[McpClient],
    direct_tool_names: set[str],
    worker_types: list[str] | None = None,
) -> list[dict]:
    """Build tool schemas for the manager agent."""
    all_descriptions = build_all_tool_descriptions(mcp_clients)
    manager_tools = [build_delegate_task_schema(all_descriptions, worker_types)]
    manager_tools.append(LOAD_TOOL_SCHEMA)
    for mcp_client in mcp_clients:
        manager_tools.extend(build_direct_tool_schemas(mcp_client, direct_tool_names))
    return manager_tools


def build_all_tool_descriptions(mcp_clients: list[McpClient]) -> list[tuple[str, str]]:
    """Build (prefixed_name, description) pairs for all tools from all servers."""
    descriptions: list[tuple[str, str]] = []
    for mcp_client in mcp_clients:
        for name, desc in mcp_client.tool_descriptions:
            descriptions.append((f"{mcp_client.server_id}:{name}", desc))
    return descriptions


def build_tool_description_list(tools: list[tuple[str, str]]) -> str:
    """Formats a list of tool tuples into a newline-separated string.

    Args:
        tools: List of (tool_name, tool_description) tuples

    Returns:
        Newline-separated string of tool descriptions in format "- name: description"
    """
    return "\n".join(f"- {name}: {desc}" for name, desc in tools)


def build_system_prompt(template: str, tool_lines: str, **kwargs) -> str:
    """Builds a system prompt by formatting the template with tool lines and optional kwargs.

    Args:
        template: The prompt template string (should contain {tool_lines} placeholder)
        tool_lines: The formatted tool descriptions string
        **kwargs: Additional keyword arguments to format into the template

    Returns:
        The formatted system prompt string
    """
    return template.format(tool_lines=tool_lines, **kwargs)


def create_agent(name: str, system_prompt: str, context: LlmContext) -> Agent:
    """Factory function to create an Agent instance.

    Args:
        name: The name for the agent
        system_prompt: The system prompt for the agent
        context: The LlmContext for the agent

    Returns:
        A new Agent instance
    """
    return Agent(name=name, system_prompt=system_prompt, context=context)


def create_llm_context(
    name: str,
    model: str,
    server_id: str | None = None,
    tools_schema: list[dict] | None = None,
    tool_executor: Callable[[str, dict], Awaitable[str]] | None = None,
) -> LlmContext:
    """Factory function to create an LlmContext instance.

    Args:
        name: The name for the context
        model: The model name to use
        server_id: Optional server identifier
        tools_schema: Optional list of tool schema dictionaries
        tool_executor: Optional tool executor

    Returns:
        A new LlmContext instance
    """
    return LlmContext(
        name=name,
        model=model,
        server_id=server_id,
        tools_schema=tools_schema or [],
        tool_executor=tool_executor,
    )
