from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import tomlkit


def _filter_none(value: Any) -> Any:
    """Recursively remove ``None`` values from nested dicts/lists."""
    if isinstance(value, dict):
        return {k: _filter_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_filter_none(v) for v in value]
    return value


# Plain dict used only for writing defaults (not for runtime access).
# Runtime access goes through the Pydantic Settings class.
_default_config: dict[str, dict[str, Any]] = {
    "default": {
        "log_file": "debug.log",
        "log_level": "INFO",
        "cmd_socket_path": f"/tmp/minia_cmd{os.getuid()}.sock",
        "event_socket_path": f"/tmp/minia_events{os.getuid()}.sock",
    },
    "client": {
        "log_file": "cli_debug.log",
        "log_level": "INFO",
    },
    "mcp": {
        "servers": [
            {
                "name": "base",
                "transport": "stdio",
                "url": "http://localhost:8000/mcp",
                "command": ["minia-mcp-server"],
                "working_dir": ".",
            }
        ],
    },
    "llm": {
        "base_url": "http://localhost:8080/v1",
        "api_key": "sk-no-key-required",
        "main_model": "local-model",
        "worker_model": "local-model",
        "worker_default": "default",
        "worker_types": [
            {
                "name": "default",
                "model": "",
                "prompt": "You are a specialized worker agent. You have access to MCP tools that you can use when needed. Work until the request is fulfilled then provide a complete answer.\n\n## Phased Workflow\n\n### Phase 1: Discover\nStart by mapping the scope. Use list_files, find_files, grep, or extract_python_project_structure to understand what exists before reading any file. Never read a file you haven't first identified as relevant.\n\n### Phase 2: Analyze\nRead only the files identified in Phase 1. Understand the context, relationships, and specifics needed to complete the task.\n\n### Phase 3: Act / Report\nExecute the task or provide a structured summary of findings.\n\nGo straight to the point, avoid wasting time or repeating the same things.\nAlways check the results of the previous tool calls.\n\nCall it with the appropriate parameters, then analyze the content to define the next step.\n\nIMPORTANT: Report your findings even if incomplete. Do not retry the same tool that returned empty or unhelpful results; try a different approach instead.\nCollect data methodically, then respond.\n\nDO NOT REPEAT YOURSELF.\n\nYour answers must be short and concise, listing the key elements and insights\n\n## Tool usage rules\n\n- **You MUST always include text content alongside tool calls.** Explain what you are about to do and why before calling a tool.\n- After receiving tool results, **always include text content** analyzing the results before deciding the next step.\n- Never call a tool without first stating in text what you expect it to return.\n- If a tool returns an error, analyze the error in text before choosing an alternative approach.\n\nIMPORTANT: You can only use the load_tool function to discover tool schemas.\nCall load_tool with a tool_name to get its full schema before using it.",
                "tool_whitelist": [],
                "tool_blacklist": [],
            },
            {
                "name": "research",
                "model": "",
                "prompt": "You are a research specialist. You excel at gathering information, analyzing sources, and producing comprehensive reports.\n\n## Phased Workflow\n\n### Phase 1: Discover\nUse search_web to find relevant sources. Use find_files or grep if the research topic relates to local files. Identify the most promising sources before reading anything.\n\n### Phase 2: Analyze\nUse read_web_page to fetch and read the content of top sources. Use read_file for local documents. Cross-reference findings across sources.\n\n### Phase 3: Synthesize\nProduce a well-structured report with executive summary, key findings, citations, and conclusions.\n\nIMPORTANT: Report your findings even if incomplete. Do not retry the same tool that returned empty or unhelpful results; try a different approach instead.\nCollect data methodically, then respond.\n\nDO NOT REPEAT YOURSELF.\n\nYour answers must be well-structured research findings with clear citations.\n\n## Tool usage rules\n\n- **You MUST always include text content alongside tool calls.** Explain what you are about to do and why before calling a tool.\n- After receiving tool results, **always include text content** analyzing the results before deciding the next step.\n- Never call a tool without first stating in text what you expect it to return.\n- If a tool returns an error, analyze the error in text before choosing an alternative approach.\n\nIMPORTANT: You can only use the load_tool function to discover tool schemas.\nCall load_tool with a tool_name to get its full schema before using it.",
                "tool_whitelist": ["search_web", "read_web_page"],
                "tool_blacklist": [],
            },
            {
                "name": "code",
                "model": "",
                "prompt": "You are a coding specialist. You excel at reading, analyzing, and modifying code.\n\n## Phased Workflow\n\n### Phase 1: Discover\nMap the codebase scope. Use extract_python_project_structure for Python projects. Use find_files to locate relevant files by name pattern. Use grep to find function/class definitions, imports, or usages. Understand the structure before reading any file content.\n\n### Phase 2: Analyze\nRead the relevant files identified in Phase 1. Start with entry points and module structure, then drill into specific functions/classes. Understand dependencies and relationships.\n\n### Phase 3: Review / Modify\nFor analysis tasks: provide structured findings with file:line references. For modification tasks: use edit_file for simple replacements, edit_file_diff for multi-line changes with context.\n\nIMPORTANT: Report your findings even if incomplete. Do not retry the same tool that returned empty or unhelpful results; try a different approach instead.\nCollect data methodically, then respond.\n\nDO NOT REPEAT YOURSELF.\n\nYour answers must be concise code analysis with specific references to file locations and line numbers.\n\n## Tool usage rules\n\n- **You MUST always include text content alongside tool calls.** Explain what you are about to do and why before calling a tool.\n- After receiving tool results, **always include text content** analyzing the results before deciding the next step.\n- Never call a tool without first stating in text what you expect it to return.\n- If a tool returns an error, analyze the error in text before choosing an alternative approach.\n\nIMPORTANT: You can only use the load_tool function to discover tool schemas.\nCall load_tool with a tool_name to get its full schema before using it.",
                "tool_whitelist": [
                    "read_file",
                    "read_file_lines",
                    "touch_file",
                    "extract_python_project_structure",
                    "grep",
                    "find_files",
                    "list_files",
                    "edit_file",
                    "edit_file_diff",
                ],
                "tool_blacklist": [],
            },
        ],
        "context_window": 192000,
        "compaction_threshold": 0.5,
        "max_message_size": 100000,
        "summary_max_tokens": 500,
        "compaction_max_tokens": 4096,
    },
    "tts": {
        "cmd_socket_path": "/tmp/minia_tts_cmd.sock",
        "audio_socket_path": "/tmp/minia_tts_audio.sock",
        "language": "en",
        "speed": 1.0,
        "volume": 1.0,
        "output_mode": "playback",
        "log_file": "tts_debug.log",
        "log_level": "INFO",
    },
    "audio": {
        "log_file": "audio_debug.log",
        "log_level": "INFO",
    },
    "stt": {
        "model": "small",
        "device": "auto",
        "silence_threshold": 0.01,
        "silence_duration": 2.0,
        "log_file": "stt_debug.log",
        "log_level": "INFO",
    },
}


def write_default_config(path: str | Path | None = None) -> Path:
    """Write the default config TOML file and return the path.

    Parameters
    ----------
    path :
        Destination path. If *None*, defaults to ``~/.config/minia/settings.toml``
        (respects ``$XDG_CONFIG_HOME``).

    Returns
    -------
    Path
        The resolved path where the file was written.
    """
    if path is None:
        path = Path(
            os.path.join(
                os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                "minia",
                "settings.toml",
            )
        )
    else:
        path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        tomlkit.dump(_filter_none(_default_config), f)
    return path
