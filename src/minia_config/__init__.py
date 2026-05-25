import os
import sys
from typing import Any
import tomllib

__all__ = ["config"]

# Default configuration
default_config: dict[str, dict[str, Any]] = {
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
                "label": None,
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
        "cmd_socket_path": os.environ.get(
            "MINIA_TTS_CMD_SOCKET", "/tmp/minia_tts_cmd.sock"
        ),
        "audio_socket_path": os.environ.get(
            "MINIA_TTS_AUDIO_SOCKET", "/tmp/minia_tts_audio.sock"
        ),
        "voice": None,
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
        "language": None,
        "silence_threshold": 0.01,
        "silence_duration": 2.0,
        "log_file": "stt_debug.log",
        "log_level": "INFO",
    },
}


# Load configuration
config_path = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "minia",
    "settings.toml",
)
loaded_config: dict[str, Any] = {}

if os.path.exists(config_path):
    try:
        with open(config_path, "rb") as f:
            loaded_config = tomllib.load(f)
    except Exception as e:
        print(f"Warning: Could not load config file: {e}", file=sys.stderr)
else:
    # Write a default config file if it doesn't exist
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as config_file:
        for section in default_config.keys():
            config_file.write(f"[{section}]\n")
            for key, value in default_config[section].items():
                if isinstance(value, list):
                    value_str = "[" + ", ".join(repr(v) for v in value) + "]"
                else:
                    value_str = repr(value)
                config_file.write(f"{key} = {value_str}\n")
            config_file.write("\n")


class ConfigItem:
    def __getitem__(self, key):
        raise TypeError(f"'{type(self).__name__}' object is not subscriptable")

    def __getattr__(self, index):
        try:
            value = self[index]
        except (KeyError, IndexError):
            return None
        if isinstance(value, dict):
            return ConfigObject(value)
        elif isinstance(value, list):
            return ConfigList(value)
        return value


class ConfigList(list, ConfigItem):
    def __iter__(self):
        for item in super().__iter__():
            if isinstance(item, dict):
                yield ConfigObject(item)
            elif isinstance(item, list):
                yield ConfigList(item)
            else:
                yield item

    def __getitem__(self, key):
        item = super().__getitem__(key)
        if isinstance(item, dict):
            return ConfigObject(item)
        elif isinstance(item, list):
            return ConfigList(item)
        return item

    def copy(self):
        return ConfigList(super().copy())


class ConfigObject(dict, ConfigItem):
    def copy(self):
        return ConfigObject(super().copy())


# Merge configurations
def deep_merge(
    base: ConfigObject, override: dict[str, Any] | ConfigItem
) -> ConfigObject:
    result: ConfigObject = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return ConfigObject(result)


co1 = ConfigObject(default_config)
co2 = ConfigObject(loaded_config)
config = deep_merge(co1, co2)
