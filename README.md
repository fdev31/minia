# MinIA/Minha — Your Mini AI

Aims at being a great AI personal assistant. Local first.

A modular, multi-process AI assistant system with streaming LLM responses, text-to-speech (TTS), speech-to-text (STT), and MCP tool integration. Built for simplicity and extensibility.

The idea is to have easy testable services communicating with each other using simple commands and broadcast notifications.
Should be easy to tweak the prompts (for now you need to directly edit src/minia/prompts.py).
Everything is (attempted to be) kept as simple as possible, avoiding an uncontrollably big code base.

MinIA uses a two-tier agent architecture (Manager + Worker) with Unix domain socket IPC, supporting real-time streaming responses, audio output, and a web interface.

## Maturity

Priorities (from top priority to least important):

- server (mcp, state machine, context handling, delegation, etc...)
- cli (simple interface to use the server)
- tts (autonomous tts service)
- chatloop (bridges tts and the server)
- stt (allows voice input)
- web (alternative client, supporting REPL and voice, TTS only for now)

## Prerequisites

- **Python 3.13** (required)
- **[uv](https://docs.astral.sh/uv/)** — the fast Python package installer and resolver
- An **OpenAI-compatible LLM server** (e.g., vLLM, Ollama, LM Studio) exposing an API endpoint at `http://localhost:8080/v1` (configurable)

## Installation

### Install uv

```bash
# macOS / Linux / WSL
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then restart your terminal or run `source ~/.bashrc` (or equivalent) to make `uv` available.

### Install MinIA

```bash
uv sync --editable --extra <extras>
```

Install only what you need — each extra adds optional functionality:

| Extra | Dependencies | Provides |
|---|---|---|
| `mcp` | `mcp`, `ddgs`, `html2text`, `diff-match-patch` | MCP server client + built-in tools (web search, file editing, command execution, geolocation) |
| `tts` | `kokoro`, `numpy`, `huggingface-hub`, `sounddevice`, `langid` | Text-to-speech using Kokoro-82M (54 voices, 9 languages) |
| `stt` | `openai-whisper`, `sounddevice`, `numpy` | Speech-to-text using OpenAI Whisper |
| `jp` | `phonemizer-fork`, `fugashi`, `unidic`, `pyopenjtalk`, `mojimoji`, `jaconv` | Japanese TTS support (g2p pipeline with unidic dictionary) |
| `dev` | `mypy`, `pytest`, `pytest-asyncio`, `ruff` | Development tooling (linting, type checking, testing) |

Example — full install with all features:

```bash
uv sync --editable --extra tts,stt,mcp,dev
```

> **Note:** If you install the `jp` extra, you willl need `unidic`. Download it after installation:
> ```bash
> uv run python -m unidic download
> ```

## Configuration

On first run, MinIA auto-generates a config file at `~/.config/minia/settings.toml`. You can edit it to customize behavior.

### Key settings

```toml
[default]
log_file = "debug.log"                   # Log file path
log_level = "INFO"                       # Logging level

[llm]
base_url = "http://localhost:8080/v1"   # OpenAI-compatible endpoint
api_key = "sk-no-key-required"           # Your API key (or placeholder)
main_model = "local-model"               # Model used by the Manager agent
worker_model = "local-model"             # Model used by Worker agents
max_history_turns = 6                    # Keep last N conversation turns
context_window = 192000                  # Max context tokens
compaction_threshold = 0.5               # Fraction of window to trigger compaction
max_message_size = 100000                # Max message size (chars) before summarization
summary_max_tokens = 500                 # Max tokens for message summarization
compaction_max_tokens = 4096             # Max tokens for context compaction

[mcp]
[[mcp.servers]]
transport = "stdio"                      # stdio, sse, or http
url = "http://localhost:8000/mcp"        # Server URL (for sse/http transports)
command = ["minia-mcp-server"]           # Command to run the MCP server (for stdio)
working_dir = "."                        # Working directory for stdio servers
label = "default"                        # Server identifier

[[mcp.servers]]
transport = 'stdio'
command = ['npx', "-y", "@a-bonus/google-docs-mcp" ]
working_dir = '/tmp'
env = { GOOGLE_CLIENT_ID = "XXX.googleusercontent.com", GOOGLE_CLIENT_SECRET = "GOXXX" }

[tts]
voice = "af_heart"                       # Kokoro voice name (see list_voices)
language = "en"                          # ISO 639-1 language code (en, ja, pt, fr, es, hi, it, zh)
speed = 1.0                              # Speech rate (0.5 - 2.0)
volume = 1.0                             # Volume (0.0 - 2.0)
output_mode = "playback"                 # "playback", or "stream" or "both" (playback=raw audio, eg: for web speech, stream=text)
log_file = "tts_debug.log"               # TTS server log file
log_level = "INFO"                       # TTS server log level

[stt]
model = "small"                          # Whisper model size (tiny, base, small, medium, large)
device = "auto"                          # "auto", "cpu", or "cuda"
silence_threshold = 0.01                 # Audio threshold for voice detection
silence_duration = 2.0                   # Seconds of silence to end recording
log_file = "stt_debug.log"               # STT log file
log_level = "INFO"                       # STT log level

[audio]
log_file = "audio_debug.log"             # Audio listener log file
log_level = "INFO"                       # Audio listener log level

[client]
log_file = "cli_debug.log"               # Client log file
log_level = "INFO"                       # Client log level
```

> **Note:** The `jp` extra is required for Japanese TTS (`language = "ja"`). Without it, Japanese text will fall back to English synthesis.

## Quick Start

### All-in-one (recommended)

```bash
just mother          # Start server + TTS + chatloop (TUI)
just mother --web    # Start server + TTS + web interface
```

This uses the **mother-forker** orchestrator, which starts all services in the correct dependency order and monitors them.

Web and stt are not finished and will likely not work. at all.

### Individual services

| Command | What it does |
|---|---|
| `just serve` | Start the LLM agent server only |
| `just tts` | Start the TTS server only |
| `just cli` | Start the terminal chat client (requires server running) |
| `just audio` | Start the audio listener (requires server + TTS running) |
| `just web` | Start the web interface (requires server + TTS running) |
| `just stt` | Start speech-to-text (requires server running) |
| `just speak "hello"` | Synthesize text via TTS CLI |
| `just stop-speak` | Stop current TTS playback |

### Using the client

Once the server is running, launch a client:

```bash
just cli          # Terminal chat (recommended)
# or visit http://localhost:9999 in your browser
```

The terminal client supports slash commands:

| Command | Aliases | Description |
|---|---|---|
| `/help` | `-h` | Show available commands |
| `/clear` | `-c` | Clear chat history |
| `/compact` | — | Force context compaction |
| `/status` | — | Show connection status |
| `/exit` | `-e`, `quit`, `q` | Exit the client |

Keyboard shortcuts:

| Shortcut | Description |
|---|---|
| `Ctrl+Q` | Exit |
| `Ctrl+O` | Toggle focus between input and output |
| `Escape` | Focus input field |
| `Ctrl+Up/Down` | Scroll output |
| `PageUp/PageDown` | Page scroll |
| `Ctrl+End` | Scroll to bottom |

### Speech-to-text

```bash
just stt    # Records from microphone, transcribes, sends to server
```

Requires a microphone. Configure the model size in `settings.toml` under `[stt]`.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │            minia (mother-forker)            │
                    │  (orchestrates all services in dependency   │
                    │   order, monitors processes, handles SIGINT)│
                    └────────┬──────────────┬─────────────────────┘
                             │              │
              ┌──────────────┘              └───────────────┐
              │                                             │
    ┌─────────▼─────────┐                         ┌─────────▼──────┐
    │   minia-server    │                         │    minia-tts   │
    │   (LLM agent)     │                         │  (Kokoro TTS)  │
    └─────────┬─────────┘                         └───────┬────────┘
              │                                           │
     ┌────────┴────────┐                           ┌──────┴──────┐
     │   cmd socket    │                           │  cmd socket │
     │  (JSON-lines)   │                           │ (JSON-lines)│
     └────────┬────────┘                           └──────┬──────┘
              │                                           │
     ┌────────┴────────┐                           ┌──────┴──────┐
     │  events socket  │                           │ audio socket│
     │  (JSON-lines)   │                           │  (PCM audio)│
     └────────┬────────┘                           └─────────────┘
              │
     ┌────────┴─────────────────────────────────────────────────┐
     │              Event socket (broadcast, persistent)        │
     └────────┬─────────────┬──────────────┬────────────────────┘
              │             │              │
     ┌────────▼──┐  ┌───────▼──────┐  ┌────▼────────────┐
     │  minia-   │  │  minia-web   │  │  minia-chatloop │
     │  client   │  │  (browser)   │  │  (audio bridge) │
     │ (commands)│  │  (events +   │  │  (events +      │
     └───────────┘  │  audio)      │  │  audio playback)│
                    └──────────────┘  └─────────────────┘
                           │
                  ┌────────▼──────────┐
                  │  minia-stt        │
                  │  (speech-to-text) │
                  │  → cmd socket     │
                  └───────────────────┘
```

### Services

| Service | Description |
|---|---|
| **minia-server** | Core LLM agent server. Runs the Manager agent, manages Unix sockets, handles streaming responses |
| **minia-tts** | Text-to-speech server using Kokoro-82M. Synthesizes audio and broadcasts to connected clients |
| **minia-chatloop** | Audio listener that bridges event socket messages to TTS playback |
| **minia-client** | Terminal TUI chat client using prompt_toolkit and rich |
| **minia-web** | Web interface served at `http://localhost:9999` with WebSocket + audio streaming |
| **minia-stt** | Speech-to-text client using OpenAI Whisper. Records from mic and sends transcriptions |
| **minia-mcp-server** | Built-in MCP server providing tools (filesystem, web search, code editing, command execution) |

### Agent Architecture

MinIA uses a **two-tier agent pattern**:

- **Manager** — the main agent that interacts with the user. Delegates complex tasks to Workers, tracks progress, and can use tools directly for simple operations.
- **Worker** — a fresh agent created per delegated task. Has access to MCP tools for file operations, web search, code execution, etc.

Context is managed via **compaction**: when the conversation exceeds a configurable threshold, the middle of the history is summarized by the LLM, preserving recent messages and the system prompt.

### Communication

MinIA uses **Unix domain sockets** for inter-process communication:

| Socket | Purpose | Transport |
|---|---|---|
| `cmd` (command) | Fire-and-forget commands (input, clear, tts_stop) | JSON-lines |
| `events` | Persistent streaming of LLM events | JSON-lines |
| `tts_cmd` | TTS synthesis/stop/settings | JSON-lines |
| `tts_audio` | Raw PCM audio broadcast | Binary frames |

See [SOCKET_PROTOCOL.md](SOCKET_PROTOCOL.md) for the full protocol specification.

## MCP Tools

The built-in MCP server provides these tools:

### File operations
`read_file`, `write_file`, `grep`, `list_files`, `find_files`, `create_directory`, `delete_file`, `move_file`, `copy_file`, `get_file_info`

### Code editing
`edit_file` — exact string replacement with occurrence counting
`edit_file_diff` — apply unified diffs with fuzzy matching

### Python project analysis
`extract_python_project_structure` — analyze Python code structure (imports, functions, classes, method signatures)

### Web
`search_web` — search the web (via DuckDuckGo)
`read_web_page` — fetch and convert a URL to text

### Location and time
`get_current_location` — IP-based geographic location (city, region, country, coordinates)
`get_current_time` — current date and timezone information
`get_full_context` — combines time + location into a single context dict

### Command execution
`execute_command` — run shell commands with timeout protection

## Deployment

### systemd

Three systemd units are provided in `systemd-units/`:

```bash
# Copy units to systemd directory
sudo cp systemd-units/minia-server.service /etc/systemd/system/
sudo cp systemd-units/minia-tts.service /etc/systemd/system/
sudo cp systemd-units/minia-chatloop.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now minia-server minia-tts minia-chatloop
```

Adjust `WorkingDirectory` and `ExecStart` paths in the unit files to match your setup.

## Troubleshooting

**TTS voice not found / falls back to English:**
Check that the voice name in `settings.toml` under `[tts].voice` matches one of the 54 Kokoro voices. Run `minia-tts-client list_voices` to see available voices.

**Japanese TTS not working:**
1. Install the `jp` extra: `uv sync --editable --extra jp`
2. Download the unidic dictionary: `uv run python -m unidic download`
3. Set `language = "ja"` in `[tts]`

**STT not recording:**
Ensure your system has a working microphone and `sounddevice` is installed (via `stt` extra). Check audio permissions.

**LLM connection errors:**
Verify your OpenAI-compatible server is running and reachable at the `base_url` configured in `[llm]`. Test with:
```bash
curl http://localhost:8080/v1/models
```

**Socket already in use:**
Old socket files may remain. Clean them up:
```bash
rm -f /tmp/minia_cmd*.sock /tmp/minia_events*.sock /tmp/minia_tts*.sock
```

**Context compaction not happening:**
Check the `compaction_threshold` setting. The default is `0.5` (50% of context window). Compaction only triggers after the threshold is exceeded.

**Config file has invalid TOML (single quotes):**
The auto-generated config uses Python `repr()` which produces single-quoted values (invalid TOML). Edit the file to use double quotes or remove the auto-generated file and let it regenerate after fixing the first-run code path.
