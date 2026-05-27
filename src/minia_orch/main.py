"""MiniAI Orchestrator — bootstrap, manager agent, and server startup."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from minia_config import config
from minia_agent import run_server
from minia_tools import McpClient, process_delegation
from minia_tools.utils import (
    build_tool_description_list,
    build_tool_executor,
    build_manager_tools_schema,
    build_all_tool_descriptions,
    create_agent,
    create_llm_context,
    build_system_prompt,
)
from minia_utils.logging import get_logger

logger = get_logger(__name__)


def _resolve_server_names(servers: Sequence[dict | object]) -> list[str]:
    """Resolve unique server names from config, deduplicating with numeric suffixes."""
    name_counts: dict[str, int] = {}
    resolved: list[str] = []
    for server in servers:
        base = getattr(server, "name", None) or "service"
        if base not in name_counts:
            name_counts[base] = 0
            resolved.append(base)
        else:
            name_counts[base] += 1
            resolved.append(f"{base}{name_counts[base]}")
    return resolved


async def _main():
    logger.info(
        "Starting | cmd=%s | events=%s",
        config.default.cmd_socket_path,
        config.default.event_socket_path,
    )

    mcp_clients: list[McpClient] = []
    all_clients: dict[str, McpClient] = {}

    async with contextlib.AsyncExitStack() as stack:
        server_names = _resolve_server_names(config.mcp.servers)
        for i, mcp_config in enumerate(config.mcp.servers):
            server_id = server_names[i]
            mcp_client = McpClient(
                transport=mcp_config.transport,
                server_url=mcp_config.url,
                server_command=mcp_config.command,
                server_env=mcp_config.env,
                server_cwd=mcp_config.working_dir,
                server_id=server_id,
            )
            await stack.enter_async_context(mcp_client)
            mcp_clients.append(mcp_client)
            all_clients[server_id] = mcp_client
            logger.info(
                "[Server] MCP connected | server_id=%s | transport=%s | tools=%d",
                server_id,
                mcp_client.transport,
                len(mcp_client.tool_descriptions),
            )

        direct_tool_names = {
            "listDir",
            "fileRead",
        }
        worker_type_names = [wt.name for wt in config.llm.worker_types] or ["default"]
        global_blacklist = config.llm.tool_blacklist
        manager_tools_schema = (
            build_manager_tools_schema(
                mcp_clients, direct_tool_names, worker_type_names, global_blacklist
            )
            if mcp_clients
            else [{}]
        )

        composite_ctx = create_llm_context(
            name="Manager",
            model=config.llm.main_model,
            tools_schema=manager_tools_schema,
        )
        shared_executor = build_tool_executor(composite_ctx, all_clients)

        async def manager_executor(func_name: str, args: dict) -> str:
            if func_name == "delegate_task":
                result = await process_delegation(args, all_clients, composite_ctx)
                return str(result)
            return await shared_executor(func_name, args)

        composite_ctx.tool_executor = manager_executor

        all_tool_descriptions = build_all_tool_descriptions(
            mcp_clients, global_blacklist
        )
        composite_prompt = build_system_prompt(
            config.prompts.MANAGER_PROMPT,
            build_tool_description_list(all_tool_descriptions),
            tool_result_snippet=config.prompts.get_tool_result_snippet(
                config.llm.tool_format
            ),
        )

        composite_agent = create_agent(
            name="Manager",
            system_prompt=composite_prompt,
            context=composite_ctx,
        )

        all_agents = [composite_agent]

        await run_server(
            all_agents, config.default.cmd_socket_path, config.default.event_socket_path
        )


def main():
    from minia_utils.logging import configure_logging

    configure_logging(log_level=config.default.log_level or "INFO", add_console=True)
    asyncio.run(_main())
