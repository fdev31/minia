"""MiniAI — compatibility shim re-exporting from split packages.

Usage:
    from minia import Agent, config, McpClient, main
    from minia_agent import Agent, run_server
    from minia_llm.model import LlmContext
    from minia_tools import McpClient, McpWorker, process_delegation
    from minia_orch.main import main
"""

from minia_agent import Agent, run_server
from minia_agent.agent import Agent as AgentClass
from minia_agent import compaction, response_stream
from minia_llm.model import ResponseData, LlmContext
from minia_llm.llm_client import get_client, ConnectionError, TimeoutError, Error
from minia_protocol import EventType
from minia_config import config
from minia_tools.utils import (
    build_system_prompt,
    build_tool_description_list,
    create_agent,
    create_llm_context,
)
from minia_tools import McpClient, McpWorker, process_delegation
from minia_tools.utils import (
    build_tool_executor,
    build_worker_tools_schema,
    build_manager_tools_schema,
    build_all_tool_descriptions,
)
from minia_tools.worker import build_worker_executor
from minia_orch.main import main, _main, process_delegation as orch_process_delegation
from minia_llm.token_estimation import estimate_tokens
from minia_llm.serialization import ToolResult, serialize
from minia_agent.server import (
    process_loop,
    _drain_queue_and_broadcast,
)

__all__ = [
    # agent
    "Agent",
    "AgentClass",
    "run_server",
    "compaction",
    "response_stream",
    # model
    "ResponseData",
    "LlmContext",
    # llm client
    "get_client",
    "ConnectionError",
    "TimeoutError",
    "Error",
    # protocol
    "EventType",
    # config
    "config",
    # tools
    "McpClient",
    "McpWorker",
    "process_delegation",
    "build_worker_executor",
    # utils
    "build_system_prompt",
    "build_tool_description_list",
    "create_agent",
    "create_llm_context",
    "build_tool_executor",
    "build_worker_tools_schema",
    "build_manager_tools_schema",
    "build_all_tool_descriptions",
    # orchestration
    "main",
    "_main",
    "orch_process_delegation",
    # token estimation
    "estimate_tokens",
    # serialization
    "ToolResult",
    "serialize",
    # server
    "process_loop",
    "_drain_queue_and_broadcast",
]
