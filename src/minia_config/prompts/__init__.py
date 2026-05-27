"""Canonical prompt definitions."""

from .manager import MANAGER_PROMPT as MANAGER_PROMPT
from .system import (
    SUMMARY_PROMPT as SUMMARY_PROMPT,
    TOOL_RESULT_SNIPPETS as TOOL_RESULT_SNIPPETS,
    WORKER_SUGGESTED_TOOL as WORKER_SUGGESTED_TOOL,
    get_tool_result_snippet as get_tool_result_snippet,
)
from .workers import (
    BUILTIN_WORKER_PROMPTS as BUILTIN_WORKER_PROMPTS,
    CODE_WORKER_PROMPT as CODE_WORKER_PROMPT,
    DEFAULT_WORKER_PROMPT as DEFAULT_WORKER_PROMPT,
    RESEARCH_WORKER_PROMPT as RESEARCH_WORKER_PROMPT,
)


def get_worker_prompt(worker_type: str) -> str:
    return BUILTIN_WORKER_PROMPTS.get(worker_type, BUILTIN_WORKER_PROMPTS["default"])
