from __future__ import annotations

import logging

from minia import prompts
from minia_config import config
from minia_mcp_client import McpClient
from minia_protocol import EventType
from .utils import (
    build_all_tool_descriptions,
    build_system_prompt,
    build_tool_description_list,
    create_agent,
    create_llm_context,
    build_worker_tools_schema,
)

logger = logging.getLogger(__name__)


def _build_worker_system_prompt(tool_descriptions: list[tuple[str, str]]) -> str:
    """Build the Worker's system prompt with tool list and folding instructions."""
    tool_list = build_tool_description_list(tool_descriptions)
    base = build_system_prompt(
        prompts.WORKER_PROMPT,
        tool_list,
        tool_result_snippet=prompts.get_tool_result_snippet(config.llm.tool_format),
    )
    base += "\nIMPORTANT: You can only use the load_tool function to discover tool schemas. "
    base += "Call load_tool with a tool_name to get its full schema before using it."
    return base


class McpWorker:
    """A worker agent that uses MCP tools via an McpClient connection."""

    def __init__(
        self,
        all_clients: dict[str, McpClient],
        suggested_tool: str | None = None,
    ):
        self.all_clients = all_clients
        self.suggested_tool = suggested_tool

    async def run(self, task: str) -> str:
        """Run the task with a fresh Agent that has MCP tool capabilities."""
        all_descriptions = build_all_tool_descriptions(list(self.all_clients.values()))

        worker_ctx = create_llm_context(
            name="Worker",
            model=config.llm.worker_model,
            tools_schema=build_worker_tools_schema(),
        )
        worker_ctx.tool_executor = build_worker_executor(self.all_clients, worker_ctx)

        agent = create_agent(
            name="Worker",
            system_prompt=_build_worker_system_prompt(all_descriptions),
            context=worker_ctx,
        )
        full_text = ""
        async for chunk in agent.run_streaming(task):
            if chunk.type in (EventType.TEXT, EventType.FINAL):
                full_text += chunk.content
        logger.info("[Worker] Task complete: response_len=%d", len(full_text))
        return full_text


def build_worker_executor(
    all_clients: dict[str, McpClient],
    ctx,
):
    """Build a worker-specific executor (same as shared, imported from utils)."""
    from .utils import build_tool_executor

    return build_tool_executor(ctx, all_clients)
