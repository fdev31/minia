# Socket Protocols

Minia uses three Unix domain sockets for inter-process communication:

| Socket | Purpose | Transport |
|---|---|---|
| **Command** (`/tmp/minia_cmd<uid>.sock`) | Fire-and-forget commands (input, clear, tts_stop) | JSON-lines |
| **Event** (`/tmp/minia_events<uid>.sock`) | Persistent subscription to LLM events and notifications | JSON-lines |
| **TTS** (`/tmp/minia_tts.sock`) | Text-to-speech synthesis, audio streaming | Binary frames |

```
┌──────────────┐   cmd    ┌─────────────────┐    events   ┌──────────────┐
│  minia-client│─────────►│                 │────────────►│minia-chatloop│
│  (TUI chat)  │  (send)  │   minia-server  │  (subscribe)│  (TTS bridge)│
└──────────────┘          │                 │             └──────────────┘
                          │                 │                   │  TTS Socket
┌──────────────┐   cmd    │                 │                   ▼
│  minia-stt   │─────────►│                 │            ┌──────────────────┐
│  (speech-to) │  (send)  │                 │            │  minia_tts server│
└──────────────┘          └─────────────────┘            │  (Kokoro TTS)    │
                                                         └──────────────────┘
```

---

## Command Socket

**Path:** `/tmp/minia_cmd<uid>.sock` (where `<uid>` is the current user's numeric ID)

**Transport:** JSON-lines — each message is a single JSON object followed by a newline (`\n`).

**Connection model:** Fire-and-forget. Clients open a connection, send one command, and close immediately.

### Client → Server Messages

#### `input`
Send a user message to the LLM for processing.
```json
{ "type": "input", "content": "Hello, how are you?" }
```

| Field | Type | Description |
|---|---|---|
| `content` | string | The user's message text |

#### `clear`
Clear the chat history (reset to system prompt only).
```json
{ "type": "clear" }
```

#### `tts_stop`
Request TTS stop. The server broadcasts `tts_stop` to all connected event socket clients.
```json
{ "type": "tts_stop" }
```

### Connection Lifecycle

```
Client opens connection
       │
       ▼  Client sends { "type": "input", "content": "..." }
  ┌──────────┐
  │  close   │  Connection closed immediately
  └──────────┘
```

---

## Event Socket

**Path:** `/tmp/minia_events<uid>.sock` (where `<uid>` is the current user's numeric ID)

**Transport:** JSON-lines — each message is a single JSON object followed by a newline (`\n`).

**Connection model:** Persistent subscription. Clients stay connected and receive all broadcasts.

### Server → Client Messages

#### `ready`
Sent once when a client connects and the event socket is ready.
```json
{ "type": "ready" }
```

#### `text`
Streaming text chunk from the LLM response. Multiple `text` messages are sent sequentially during a single response.
```json
{ "type": "text", "content": "Hello" }
```

| Field | Type | Description |
|---|---|---|
| `content` | string | Fragment of the LLM's response text |

#### `thinking`
Streaming thinking/reasoning chunk from the LLM (used when the model produces hidden reasoning tokens).
```json
{ "type": "thinking", "content": "Let me think about this..." }
```

| Field | Type | Description |
|---|---|---|
| `content` | string | Fragment of the thinking/reasoning text |

#### `tool_call_start`
Sent when the LLM begins invoking a tool.
```json
{
  "type": "tool_call_start",
  "tool_name": "web_search",
  "task_instruction": "Search for latest news",
  "tool_schema": {
    "function": {
      "name": "web_search",
      "description": "Search the web",
      "parameters": { "properties": { "query": { "description": "Search query" } } }
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `tool_name` | string | Name of the tool being called |
| `task_instruction` | string or null | Instruction for executing the tool |
| `tool_schema` | object or null | OpenAI-compatible tool definition |

#### `tool_call`
Sent with the result after a tool has executed.
```json
{ "type": "tool_call", "content": "Search results: ..." }
```

| Field | Type | Description |
|---|---|---|
| `content` | string | Tool execution result |

#### `final`
Sent when the LLM response is complete. Ends the current response cycle.
```json
{ "type": "final", "content": "This is the complete response." }
```

| Field | Type | Description |
|---|---|---|
| `content` | string | The final/complete response text |

#### `user_input`
Broadcast to all connected clients when any client sends input via the command socket.
```json
{ "type": "user_input", "content": "What is the weather?" }
```

| Field | Type | Description |
|---|---|---|
| `content` | string | The user's input text |

#### `cleared`
Broadcast when any client sends a `clear` command via the command socket, signaling that chat history was reset.
```json
{ "type": "cleared" }
```

#### `usage`
Token usage information, sent at the end of a response.
```json
{ "type": "usage", "tokens": 1234 }
```

| Field | Type | Description |
|---|---|---|
| `tokens` | integer | Number of tokens consumed |

#### `error`
Error message from the server.
```json
{ "type": "error", "message": "LLM server is not reachable." }
```

| Field | Type | Description |
|---|---|---|
| `message` | string | Human-readable error description |

#### `disconnected`
Broadcast when another event socket client disconnects.
```json
{ "type": "disconnected" }
```

#### `tts_stop`
Broadcast to signal all connected clients (especially audio listeners) to stop TTS playback.
```json
{ "type": "tts_stop" }
```

### Client → Server Messages

#### `tts_stop`
Request TTS stop. The server broadcasts `tts_stop` to all connected clients.
```json
{ "type": "tts_stop" }
```

#### `disconnect`
Signal the server to close this client's connection gracefully.
```json
{ "type": "disconnect" }
```

### Streaming Lifecycle

```
Client connects to event socket
       │
       ▼
  ┌──────────┐
  │  ready   │  Server sends this on connect
  └────┬─────┘
       │  (client stays connected, listening for events)
       │
       ▼  Events arrive from command socket processing
  ┌──────────┐
  │  text ×N │  LLM streaming chunks (may be interleaved with)
  │thinking×M│  LLM thinking chunks (may be interleaved with)
  │tool_call_start│  Tool invocation start
  │ tool_call │  Tool execution result
  └────┬─────┘
       │
       ▼  Server sends { "type": "final", "content": "..." }
  ┌──────────┐
  │   usage  │  Token consumption info
  └──────────┘
       │
       ▼  (response cycle complete; client continues listening)
```

### Broadcast Behavior

The server maintains a list of all connected event socket clients via `BroadcastManager`. When a command is received on the command socket, the server broadcasts the corresponding event to **all** connected event socket clients. This enables multi-client synchronization (e.g., TUI clients see each other's input, audio listeners get streaming text).

Stale/disconnected clients are automatically removed from the broadcast list when write errors occur.

---

## TTS Command Socket

**Path:** `/tmp/minia_tts_cmd.sock` (configurable via `MINIA_TTS_CMD_SOCKET` environment variable)

**Transport:** JSON-lines — each message is a single JSON object followed by a newline (`\n`).

**Connection model:** Fire-and-forget for synthesis/stop; request-response for status/settings.

### Client → Server Messages

#### `synthesize`
Send text for TTS synthesis. Server synthesizes and broadcasts audio to all audio socket clients.
```json
{ "type": "synthesize", "content": "Hello world" }
```

#### `stop`
Stop current speech synthesis and playback.
```json
{ "type": "stop" }
```

#### `settings`
Change TTS settings. Returns `{"type": "settings_ack", "key": "...", "ok": true/false}`.
```json
{ "type": "settings", "key": "voice", "value": "af_bella" }
```

Supported keys: `voice`, `language`, `speed`, `volume`

#### `status`
Get current TTS server status. Returns `{"type": "status", "data": {...}}`.
```json
{ "type": "status" }
```

#### `list_voices`
List all available voices. Returns `{"type": "voices", "data": {...}}`.
```json
{ "type": "list_voices" }
```

### Connection Lifecycle

```
Client connects
       │
       ▼  Send command
  ┌──────────┐
  │  synthesize│  Fire-and-forget (no response)
  │  stop     │  Fire-and-forget (no response)
  │  settings │  ← {"type": "settings_ack", ...}
  │  status   │  ← {"type": "status", ...}
  │  list_voices│ ← {"type": "voices", ...}
  └────┬─────┘
       │
       ▼  Connection closed
```

---

## TTS Audio Socket

**Path:** `/tmp/minia_tts_audio.sock` (configurable via `MINIA_TTS_AUDIO_SOCKET` environment variable)

**Transport:** Binary frames — raw audio data with a 2-byte sample count header.

**Connection model:** Persistent subscription. Server pushes audio frames to all connected clients.

### Wire Format

Each audio frame:
```
┌─────────────┬───────────────────┐
│ num_samples │ int16 PCM samples │
│ (2 bytes BE)│ (num_samples × 2) │
└─────────────┴───────────────────┘
```

- **num_samples:** uint16, big-endian (number of PCM samples in this chunk)
- **PCM samples:** signed 16-bit integers, little-endian
- **Sample rate:** 24000 Hz (fixed, not sent in frame)

### Server → Client Frames

#### Audio Frame
Raw PCM audio chunk. Multiple frames are sent during synthesis.
```
[num_samples:2][int16 PCM data]
```

**Example (hex):** `00 64 [pcm data...]`
- num_samples: 100
- PCM data: 100 × 2 bytes = 200 bytes of int16 samples

### Client → Server Messages

#### `disconnect`
Signal the server to close this client's connection.
```json
{ "type": "disconnect" }
```

### Connection Lifecycle

```
Client connects
       │
       ▼  Server pushes audio frames continuously
  ┌──────────────────────────────────┐
  │  ← Audio frame (num_samples + PCM)│
  │  ← Audio frame                    │
  │  ← Audio frame                    │
  │  (frames stop when synthesis done)│
  │                                  │
  │  Send { "type": "disconnect" }   │
  └────┬─────┘
       │
       ▼  Connection closed
```

---

## Configuration

Socket paths are defined in the config system (`~/.config/minia/settings.toml`):

```toml
[default]
cmd_socket_path = "/tmp/minia_cmd<uid>.sock"  # Command socket
event_socket_path = "/tmp/minia_events<uid>.sock" # Event socket

[tts]
cmd_socket_path = "/tmp/minia_tts_cmd.sock"  # TTS command socket
audio_socket_path = "/tmp/minia_tts_audio.sock" # TTS audio socket
voice = "af_heart"
language = "en"
speed = 1.0
volume = 1.0
output_mode = "both"
```

The TTS socket paths can also be overridden via the `MINIA_TTS_SOCKET`, `MINIA_TTS_CMD_SOCKET`, and `MINIA_TTS_AUDIO_SOCKET` environment variables.

---

## Inter-Socket Coordination

The `tts_stop` message bridges the command/event sockets and the TTS command socket. When any client sends `tts_stop` to either the command socket or event socket:

1. Server broadcasts `{ "type": "tts_stop" }` to all connected event socket clients
2. `minia-chatloop` (the audio listener) receives the broadcast on the event socket
3. `minia-chatloop` sends a `stop` command to the TTS command socket to interrupt playback

This allows a single `tts_stop` command from any client to stop TTS across all audio listeners.

---

## Example Flows

### Chat Session (Command + Event Sockets)

```
TUI Client ──► Cmd Server: (connect) ──► { "type": "input", "content": "What is AI?" } ──► (close)
STT Client   ──► Cmd Server: (connect) ──► { "type": "input", "content": "Hello" } ──► (close)
Cmd Server   ──► Event Server: (broadcast via queue)
Event Server ──► TUI Client: { "type": "user_input", "content": "What is AI?" }
Event Server ──► TUI Client: { "type": "text", "content": "Artificial" }
Event Server ──► TUI Client: { "type": "text", "content": " intelligence" }
Event Server ──► TUI Client: { "type": "text", "content": " (AI)" }
Event Server ──► TUI Client: { "type": "final", "content": "Artificial intelligence (AI) is..." }
Event Server ──► TUI Client: { "type": "usage", "tokens": 42 }
```

### TTS Synthesis (Command + Audio Sockets)

```
Audio Bridge ──► TTS Cmd Server: (connect) ──► { "type": "synthesize", "content": "Hi" } ──► (close)
TTS Cmd Server ──► Audio Bridge: (receives audio frames on audio socket)
Audio Bridge ──► System Speakers: (plays PCM audio)
```

### TTS CLI (Command Socket Only)

```
CLI ──► TTS Cmd Server: (connect) ──► { "type": "status" }
TTS Cmd Server ──► CLI: { "type": "status", "data": {...} }
CLI ──► TTS Cmd Server: (close)

CLI ──► TTS Cmd Server: (connect) ──► { "type": "list_voices" }
TTS Cmd Server ──► CLI: { "type": "voices", "data": {...} }
CLI ──► TTS Cmd Server: (close)

CLI ──► TTS Cmd Server: (connect) ──► { "type": "settings", "key": "voice", "value": "af_bella" }
TTS Cmd Server ──► CLI: { "type": "settings_ack", "key": "voice", "ok": true }
CLI ──► TTS Cmd Server: (close)
```

---

## Implementation Notes

### Socket Infrastructure

**Command socket** and **Event socket** both use `UnixSocketServer` from the `minia_sockets` package with JSON-lines framing.

- **`UnixSocketServer`** — Bootstrap for Unix domain socket servers with signal handling and client task management
- **`BroadcastManager`** — Fan-out message distribution to all connected event socket clients (main) and audio socket clients (TTS)

The command socket handler is stateless (fire-and-forget), while the event socket handler maintains the `BroadcastManager` client list.

### Reconnection

The event socket client supports auto-reconnect (`auto_reconnect=True`). The command socket is fire-and-forget (no reconnect needed). The TTS audio socket client supports auto-reconnect.

### Frame Size Limits

| Protocol | Limit | Details |
|---|---|---|
| Command/Event socket | None | JSON lines, arbitrary length |
| TTS command socket | None | JSON lines, arbitrary length |
| TTS audio socket | ~32KB per frame | 2-byte sample count + PCM data (24kHz, int16) |

