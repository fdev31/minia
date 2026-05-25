from __future__ import annotations

from minia import prompts
from minia_config.settings import WorkerTypeConfig
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
from minia_utils.logging import get_logger

logger = get_logger(__name__)


def _build_worker_system_prompt(
    prompt_template: str,
    tool_descriptions: list[tuple[str, str]],
) -> str:
    """Build the Worker's system prompt with tool list and folding instructions."""
    tool_list = build_tool_description_list(tool_descriptions)
    base = build_system_prompt(
        prompt_template,
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
        worker_type: str = "default",
    ):
        self.all_clients = all_clients
        self.suggested_tool = suggested_tool
        self.worker_type = worker_type

    def _resolve_worker_config(
        self,
    ) -> tuple[str, str, list[str] | None, list[str] | None]:
        """Resolve worker config from settings, falling back to built-ins."""
        wc: WorkerTypeConfig | None = None
        for wt in config.llm.worker_types:
            if wt.name == self.worker_type:
                wc = wt
                break

        if wc is not None:
            model = wc.model or config.llm.worker_model
            prompt = wc.prompt or prompts.get_worker_prompt(self.worker_type)
            return model, prompt, wc.tool_whitelist or None, wc.tool_blacklist or None

        prompt = prompts.get_worker_prompt(self.worker_type)
        return config.llm.worker_model, prompt, None, None

    async def run(self, task: str) -> str:
        """Run the task with a fresh Agent that has MCP tool capabilities."""
        all_descriptions = build_all_tool_descriptions(list(self.all_clients.values()))

        model, prompt_template, whitelist, blacklist = self._resolve_worker_config()

        worker_ctx = create_llm_context(
            name="Worker",
            model=model,
            tools_schema=build_worker_tools_schema(
                list(self.all_clients.values()),
                whitelist=whitelist,
                blacklist=blacklist,
            ),
        )
        worker_ctx.tool_executor = build_worker_executor(self.all_clients, worker_ctx)

        agent = create_agent(
            name="Worker",
            system_prompt=_build_worker_system_prompt(
                prompt_template, all_descriptions
            ),
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
