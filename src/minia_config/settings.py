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


class LlmSettings(BaseSettings):
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "sk-no-key-required"
    main_model: str = "local-model"
    worker_model: str = "local-model"
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
