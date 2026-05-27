"""Non-template worker prompts for config files."""

from .workers import (
    CODE_WORKER_PROMPT,
    DEFAULT_WORKER_PROMPT,
    RESEARCH_WORKER_PROMPT,
)

# Non-template versions: placeholders removed.
# These are the exact strings used in settings/writer config defaults.

DEFAULT_WORKER_PROMPTS: dict[str, str] = {
    "default": DEFAULT_WORKER_PROMPT.replace("{tool_lines}", "").replace(
        "{tool_result_snippet}", ""
    ),
    "research": RESEARCH_WORKER_PROMPT.replace("{tool_lines}", "").replace(
        "{tool_result_snippet}", ""
    ),
    "code": CODE_WORKER_PROMPT.replace("{tool_lines}", "").replace(
        "{tool_result_snippet}", ""
    ),
}
