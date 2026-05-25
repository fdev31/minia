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
