from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import tomllib

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

_CONFIG_DIR = Path(
    os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "minia",
        "settings.toml",
    )
)


def _load_toml_config() -> dict[str, Any]:
    """Load the TOML config file if it exists."""
    if _CONFIG_DIR.exists():
        try:
            with open(_CONFIG_DIR, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            print(f"WARNING: Corrupted TOML config at {_CONFIG_DIR}: {e}")
            print("Falling back to default settings.")
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge ``override`` into ``base``, returning a new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif (
            key in result and isinstance(result[key], list) and isinstance(value, list)
        ):
            result[key] = value  # Replace lists entirely
        else:
            result[key] = value
    return result


class DefaultSettings(BaseSettings):
    log_file: str = "debug.log"
    log_level: str = "INFO"
    cmd_socket_path: str = f"/tmp/minia_cmd{os.getuid()}.sock"
    event_socket_path: str = f"/tmp/minia_events{os.getuid()}.sock"

    model_config = SettingsConfigDict(extra="allow")


class ClientSettings(BaseSettings):
    log_file: str = "cli_debug.log"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(extra="allow")


class McpServerSettings(BaseSettings):
    name: str
    transport: str
    url: str
    command: list[str]
    working_dir: str = "."
    label: str | None = None
    env: dict[str, str] | None = None

    model_config = SettingsConfigDict(extra="allow")


class McpSettings(BaseSettings):
    servers: list[McpServerSettings] = []

    model_config = SettingsConfigDict(extra="allow")


class WorkerTypeConfig(BaseSettings):
    name: str
    model: str = ""
    prompt: str = ""
    tool_whitelist: list[str] = []
    tool_blacklist: list[str] = []

    model_config = SettingsConfigDict(extra="allow")


class LlmSettings(BaseSettings):
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "sk-no-key-required"
    main_model: str = "local-model"
    worker_model: str = "local-model"
    worker_default: str = "default"
    worker_types: list[WorkerTypeConfig] = []
    context_window: int = 192_000
    compaction_threshold: float = 0.5
    max_message_size: int = 100_000
    summary_max_tokens: int = 500
    compaction_max_tokens: int = 4_096
    parallel_tool_calls: bool = True
    tool_format: str = "yaml"

    model_config = SettingsConfigDict(extra="allow")


class TtsSettings(BaseSettings):
    cmd_socket_path: str = "/tmp/minia_tts_cmd.sock"
    audio_socket_path: str = "/tmp/minia_tts_audio.sock"
    voice: str | None = None
    language: str = "en"
    speed: float = 1.0
    volume: float = 1.0
    output_mode: str = "playback"
    log_file: str = "tts_debug.log"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(extra="allow")


class AudioSettings(BaseSettings):
    log_file: str = "audio_debug.log"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(extra="allow")


class SttSettings(BaseSettings):
    model: str = "small"
    device: str = "auto"
    language: str | None = None
    silence_threshold: float = 0.01
    silence_duration: float = 2.0
    log_file: str = "stt_debug.log"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(extra="allow")


class Settings(BaseSettings):
    default: DefaultSettings = DefaultSettings()
    client: ClientSettings = ClientSettings()
    mcp: McpSettings = McpSettings()
    llm: LlmSettings = LlmSettings()
    tts: TtsSettings = TtsSettings()
    audio: AudioSettings = AudioSettings()
    stt: SttSettings = SttSettings()

    model_config = SettingsConfigDict(
        env_file=None,
        extra="allow",
    )

    def __init__(self, **kwargs):
        # Step 1: Get env-var-resolved defaults from pydantic-settings
        # We pass empty kwargs so pydantic-settings only uses env vars + defaults
        toml_config = _load_toml_config()

        # Build the init data: defaults + TOML overrides + explicit kwargs
        # Priority: kwargs > TOML > defaults
        default_dict = self._default_dict()
        data = _deep_merge(default_dict, toml_config)
        data = _deep_merge(data, kwargs)

        # Now let pydantic-settings process env vars ON TOP of everything
        # We need to pass env var overrides as kwargs so they win
        env_overrides = self._get_env_overrides()
        data = _deep_merge(data, env_overrides)

        super().__init__(**data)

    @staticmethod
    def _default_dict() -> dict[str, Any]:
        """Return the default config as a plain dict."""
        return {
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
                "context_window": 192_000,
                "compaction_threshold": 0.5,
                "max_message_size": 100_000,
                "summary_max_tokens": 500,
                "compaction_max_tokens": 4_096,
                "tool_format": "yaml",
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

    @staticmethod
    def _get_env_overrides() -> dict[str, Any]:
        """Extract env var overrides using MINIA_ prefix convention."""
        prefix = "MINIA_"
        overrides: dict[str, Any] = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                env_key = key[len(prefix) :]  # e.g. "LLM__CONTEXT_WINDOW"
                parts = env_key.split("__")
                target = overrides
                for part in parts[:-1]:
                    part_lower = part.lower()
                    if part_lower not in target:
                        target[part_lower] = {}
                    target = target[part_lower]
                target[parts[-1].lower()] = value
        return overrides
