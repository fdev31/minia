"""McpWorker factory and process_delegation — creates agents with MCP tool capabilities."""

from __future__ import annotations

from typing import Awaitable, Callable

from minia_config.settings import WorkerTypeConfig
from minia_config import config
from minia_mcp_client.mcp_client import McpClient
from minia_tools.tool_schemas import build_delegate_task_schema
from minia_protocol import EventType
from minia_llm.model import LlmContext
from minia_tools.utils import (
    build_all_tool_descriptions,
    build_system_prompt,
    build_tool_description_list,
    create_agent,
    create_llm_context,
    build_worker_tools_schema,
    build_tool_executor,
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
        tool_result_snippet=config.prompts.get_tool_result_snippet(
            config.llm.tool_format
        ),
    )
    return base


def process_delegation(
    args,
    all_clients: dict[str, McpClient],
    manager_ctx: LlmContext | None = None,
) -> Awaitable[str]:
    """Delegate a task to a worker agent.

    This is the entry point for manager→worker delegation. It creates
    an McpWorker and runs it with the given task.
    """
    task_instruction = args.get("task_instruction", "")
    suggested_tool = args.get("tool")
    worker_type = args.get("worker_type", config.llm.worker_default)

    if worker_type != config.llm.worker_default:
        logger.info(
            "[Manager] Delegating to Worker (type: %s, tool: %s): '%s'",
            worker_type,
            suggested_tool,
            task_instruction,
        )
    elif suggested_tool:
        logger.info(
            "[Manager] Delegating to Worker (tool: %s): '%s'",
            suggested_tool,
            task_instruction,
        )
    else:
        logger.info("[Manager] Delegating to Worker: '%s'", task_instruction)

    worker = McpWorker(
        all_clients, suggested_tool=suggested_tool, worker_type=worker_type
    )
    model, _, whitelist, blacklist = worker._resolve_worker_config()
    worker_ctx = create_llm_context(
        name="Worker",
        model=model,
        tools_schema=build_worker_tools_schema(
            list(all_clients.values()),
            whitelist=whitelist,
            blacklist=blacklist,
            global_blacklist=config.llm.tool_blacklist,
        ),
    )
    if manager_ctx is not None:
        manager_ctx.delegatee_ctx = worker_ctx
    return worker.run(task_instruction, worker_ctx)


class McpWorker:
    """A worker agent that uses MCP tools via an McpClient connection.

    This is a factory: it resolves worker config, builds tools, creates an
    Agent, and runs the streaming loop. It does not subclass Agent.
    """

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
            prompt = wc.prompt or config.prompts.get_worker_prompt(self.worker_type)
            return model, prompt, wc.tool_whitelist or None, wc.tool_blacklist or None

        prompt = config.prompts.get_worker_prompt(self.worker_type)
        return config.llm.worker_model, prompt, None, None

    async def run(self, task: str, worker_ctx: LlmContext | None = None) -> str:
        """Run the task with a fresh Agent that has MCP tool capabilities."""
        all_descriptions = build_all_tool_descriptions(
            list(self.all_clients.values()), config.llm.tool_blacklist
        )
        all_descriptions.append(
            ("delegate_task", "Delegate a task to a specialized worker agent")
        )

        model, prompt_template, whitelist, blacklist = self._resolve_worker_config()

        if worker_ctx is None:
            worker_ctx = create_llm_context(
                name="Worker",
                model=model,
                tools_schema=build_worker_tools_schema(
                    list(self.all_clients.values()),
                    whitelist=whitelist,
                    blacklist=blacklist,
                    global_blacklist=config.llm.tool_blacklist,
                ),
            )
            worker_type_names = [wt.name for wt in config.llm.worker_types] or [
                config.llm.worker_default
            ]
            delegate_task_schema = build_delegate_task_schema(
                all_descriptions, worker_type_names
            )
            worker_ctx.tools_schema.append(delegate_task_schema)
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
    ctx: LlmContext,
) -> Callable[[str, dict], Awaitable[str]]:
    """Build a worker-specific executor with delegate_task support."""
    shared_executor = build_tool_executor(ctx, all_clients)

    async def worker_executor(func_name: str, args: dict) -> str:
        if func_name == "delegate_task":
            result = await process_delegation(
                args,
                all_clients,
                ctx,
            )
            return str(result)
        return await shared_executor(func_name, args)

    return worker_executor
