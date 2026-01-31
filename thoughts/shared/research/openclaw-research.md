# OpenClaw Research Document

## What is OpenClaw?

OpenClaw (formerly Clawdbot/Moltbot) is an open-source personal AI assistant platform (MIT license, TypeScript, 131k+ GitHub stars). It runs on your own devices as a persistent background daemon and acts as a general-purpose AI agent connecting to messaging channels (WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, Microsoft Teams, WebChat).

**Repository**: https://github.com/openclaw/openclaw
**Website**: https://openclaw.ai/
**Docs**: https://docs.openclaw.ai/
**Runtime**: Node >= 22 (pnpm for builds, Bun optional)

## Architecture

```
External Systems <-> HTTP/WebSocket Gateway <-> Agent(s) <-> LLM Provider(s)
                          |                        |
                     Security Layer           Tool System
                     DM Pairing               - Bash (sandboxed)
                     Auth Tokens              - Browser (CDP/Playwright)
                                              - Canvas (A2UI)
                                              - File I/O
                                              - Custom Skills
                                              - Memory Search
```

### Gateway (Control Plane)

The Gateway is the central orchestrator running as a persistent background service:

- **WebSocket server** at `ws://127.0.0.1:18789` (default)
- **HTTP server** on port 18793 for Canvas and webhooks
- Manages sessions, channels, tools, events
- Runs as daemon: systemd (Linux), launchd (macOS)
- Routes messages between CLI, web UI, nodes (devices), and messaging channels

### Agent (Reasoning Engine)

- Model-agnostic: Claude, GPT, Gemini, Ollama, etc.
- Multi-agent routing: different accounts/channels to isolated agent instances
- Workspace per agent: dedicated memory, skills, configuration
- **Recommended**: Claude Opus 4.5 for context window + prompt injection resistance

### Memory System

Uses **plain Markdown files** as source of truth:

- `MEMORY.md` - Long-term facts, preferences (loaded in private sessions)
- `memory/YYYY-MM-DD.md` - Daily append-only logs (today + yesterday loaded)
- **Vector search**: SQLite-backed (`sqlite-vec`), embeddings via OpenAI/Gemini/local
- **Hybrid search**: vector similarity + BM25 keyword matching
- Tools: `memory_search` (semantic), `memory_get` (direct)
- Silent memory flush before context compaction

### Skills System

JavaScript/TypeScript functions in `AgentSkills`-compatible directories:

```
skill-name/
├── SKILL.md          # YAML frontmatter + instructions
├── index.ts          # Implementation
└── package.json      # Dependencies
```

**Loading precedence**: Workspace skills > Managed skills (`~/.openclaw/skills`) > Bundled (100+)
**Community**: 700+ skills on ClawHub registry (`clawhub install <slug>`)

### Nodes (Device Peripherals)

Companion devices connecting via WebSocket with `role: "node"`:

- macOS menu bar, iOS, Android, headless Linux/Windows
- Capabilities: camera, screen recording, system commands, location, SMS
- Pairing: `openclaw devices approve <requestId>`

## LLM Provider Configuration

Uses `provider/model` naming: `anthropic/claude-opus-4-5`

### Built-in Providers

| Provider               | Auth                | Notes                                            |
| ---------------------- | ------------------- | ------------------------------------------------ |
| Anthropic              | `ANTHROPIC_API_KEY` | **Recommended**. Opus 4.5 best for complex tasks |
| OpenAI                 | `OPENAI_API_KEY`    | Full support                                     |
| Google Gemini          | `GEMINI_API_KEY`    | Full support                                     |
| Groq                   | API Key             | Fast inference                                   |
| Mistral, xAI, Cerebras | API Key             |                                                  |
| OpenRouter             | API Key             | Meta-provider                                    |
| Ollama                 | Auto-detected       | `http://127.0.0.1:11434/v1`                      |

### Configuration

```json
{
  "agent": {
    "model": "anthropic/claude-opus-4-5"
  }
}
```

CLI: `openclaw onboard` (wizard), `openclaw models set anthropic/claude-opus-4-5`

## API Endpoints & Integration

### 1. HTTP Tools API (Best for HUGO Backend)

**Endpoint**: `POST http://127.0.0.1:18789/tools/invoke`

```python
import httpx

async def invoke_openclaw(tool: str, args: dict, session: str = "main") -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://127.0.0.1:18789/tools/invoke",
            json={"tool": tool, "args": args, "sessionKey": session},
            headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}"}
        )
        return resp.json()

# Send message to agent
await invoke_openclaw("sessions_send", {"to": "main", "message": "What's on my calendar?"})

# Search memory
await invoke_openclaw("memory_search", {"query": "robot battery level", "limit": 5})
```

**Available tools**: `sessions_list`, `sessions_send`, `sessions_history`, `read`, `write`, `edit`, `bash`, `browser_*`, `memory_search`, `memory_get`, custom skills.

### 2. Webhook API (Event-Driven Triggers)

**Endpoint**: `POST http://127.0.0.1:18789/hooks/agent`

```python
async def trigger_openclaw_task(message: str, session_key: str = "hugo:task"):
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://127.0.0.1:18789/hooks/agent",
            json={
                "message": message,
                "sessionKey": session_key,
                "wakeMode": "now",
                "model": "anthropic/claude-opus-4-5",
                "timeoutSeconds": 300
            },
            headers={"Authorization": f"Bearer {HOOK_TOKEN}"}
        )
```

Configuration:

```json
{
  "hooks": {
    "enabled": true,
    "token": "hugo-hook-secret",
    "path": "/hooks"
  }
}
```

Other webhook endpoints:

- `POST /hooks/wake` - Trigger main session event
- `POST /hooks/<name>` - Custom mapped endpoints (e.g., GitHub webhooks)

### 3. WebSocket Protocol (Real-Time Bidirectional)

**Endpoint**: `ws://127.0.0.1:18789`

```python
import websockets, json

async def connect_openclaw():
    async with websockets.connect("ws://127.0.0.1:18789") as ws:
        # Handle challenge
        challenge = json.loads(await ws.recv())

        # Authenticate
        await ws.send(json.dumps({
            "type": "req", "id": 1, "method": "connect",
            "params": {
                "client": {"id": "hugo-backend", "role": "operator",
                           "scopes": ["operator.read", "operator.write"]},
                "auth": {"token": OPENCLAW_TOKEN}
            }
        }))
        response = json.loads(await ws.recv())

        # Send message
        await ws.send(json.dumps({
            "type": "req", "id": 2, "method": "chat.send",
            "params": {"session": "main", "message": "Hello from HUGO"}
        }))

        # Listen for events
        async for msg in ws:
            event = json.loads(msg)
            print(event)
```

**Message types**: `req`/`res` (request-response), `event` (server push)
**Key methods**: `chat.send`, `chat.history`, `sessions.list`, `system-presence`

### 4. Cron Jobs (Scheduled Automation)

```bash
openclaw cron add \
  --name "Daily Brief" \
  --cron "0 7 * * *" \
  --tz "America/Los_Angeles" \
  --session isolated \
  --message "Summarize overnight events"
```

## Security Model

### Sandboxing

```json
{
  "agents": {
    "defaults": {
      "sandbox": {
        "mode": "all",
        "workspaceAccess": "none"
      }
    }
  }
}
```

Modes: `"off"` (full access), `"all"` (Docker-isolated tools), per-tool configuration.

### Authentication

- Gateway token: `OPENCLAW_GATEWAY_TOKEN` env var or Bearer token
- DM pairing for messaging channels
- Loopback-only browser control
- Device pairing with cryptographic signatures

## Installation & Deployment

```bash
# Install
curl -fsSL https://openclaw.bot/install.sh | bash
# or: npm install -g openclaw@latest

# Onboard (wizard: model, API key, channels, daemon)
openclaw onboard --install-daemon

# Start gateway
openclaw gateway
```

**Dashboard**: `http://127.0.0.1:18789/` (web UI for chat, sessions, config)

### HUGO-Specific Config

```json
{
  "agent": {
    "model": "anthropic/claude-opus-4-5"
  },
  "gateway": {
    "bind": "loopback",
    "port": 18789
  },
  "hooks": {
    "enabled": true,
    "token": "hugo-integration-secret"
  },
  "skills": {
    "load": {
      "extraDirs": ["/Users/eduardkakosyan/HUGO/openclaw-skills"]
    }
  }
}
```

## System Requirements

- **Runtime**: Node.js >= 22
- **OS**: macOS (native), Linux, Windows (WSL2)
- **RAM**: 4GB min, 8GB+ recommended (gateway is lightweight)
- **Docker**: Recommended for sandbox isolation
- **Disk**: 10-20GB for gateway, logs, memory

## HUGO Integration Strategy

OpenClaw provides HUGO with:

1. **Persistent AI agent** with memory across sessions
2. **Multi-turn Claude reasoning** with automatic tool-calling loops
3. **HTTP + WebSocket + Webhook APIs** for programmatic control
4. **Extensible skills** for robot-specific capabilities
5. **Memory system** for storing robot context persistently
6. **Scheduled automation** via cron jobs

**Integration flow**:

```
Robot mic → STT → HUGO Backend → HTTP POST → OpenClaw → Claude → Tool calls
                                                                      |
                                                            ┌─────────┴─────────┐
                                                            ▼                   ▼
                                                     Robot actions        Memory writes
                                                     (via HUGO tools)     (persistent context)
```

HUGO Backend exposes robot capabilities as HTTP endpoints that OpenClaw calls as custom tools:

- `POST /tools/robot/move` - Move head/body/antennas
- `POST /tools/robot/look` - Camera + Gemini vision analysis
- `POST /tools/robot/speak` - TTS through robot speaker
- `POST /tools/robot/listen` - STT from robot microphone
- `POST /tools/robot/emotion` - Play pre-recorded expression

## Sources

- https://github.com/openclaw/openclaw
- https://openclaw.ai/
- https://docs.openclaw.ai/concepts/model-providers
- https://docs.openclaw.ai/concepts/memory
- https://docs.openclaw.ai/gateway/security
- https://docs.openclaw.ai/gateway/protocol
- https://docs.openclaw.ai/gateway/tools-invoke-http-api
- https://docs.openclaw.ai/automation/webhook
- https://docs.openclaw.ai/tools/skills
- https://docs.openclaw.ai/start/getting-started
