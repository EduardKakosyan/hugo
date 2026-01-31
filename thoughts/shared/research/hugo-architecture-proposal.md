# HUGO Architecture – Phase 1 Implementation

## System Overview

HUGO is a personal assistant embodied in a Reachy Mini robot. Phase 1 implements the core intelligence layer: voice I/O, vision processing, and AI reasoning via OpenClaw + Claude. Robot integration is deferred to Phase 2.

**Stack**: Python 3.12 / FastAPI / uv (backend), SvelteKit 5 / pnpm (frontend), OpenClaw + Claude Sonnet 4.5 (reasoning, via WebSocket), Gemini (vision), MLX-Audio (voice)

**Hardware**: Mac M4 Pro 48GB — runs all local models (STT, TTS, VAD) via Apple Silicon MLX framework.

---

## Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                      Mac M4 Pro (48GB)                            │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                  HUGO Backend (FastAPI :8080)                │  │
│  │                  backend/src/main.py                         │  │
│  │                                                             │  │
│  │  ┌──────────────────┐   ┌──────────────────┐               │  │
│  │  │  Voice Pipeline   │   │  Vision Service   │               │  │
│  │  │                  │   │                  │               │  │
│  │  │  Silero VAD      │   │  OpenCV Camera   │               │  │
│  │  │  MLX Whisper STT │   │  Gemini API      │               │  │
│  │  │  Kokoro TTS      │   │                  │               │  │
│  │  │  sounddevice I/O │   │                  │               │  │
│  │  └──────────────────┘   └──────────────────┘               │  │
│  │                                                             │  │
│  │  ┌──────────────────┐   ┌──────────────────┐               │  │
│  │  │  Bridge Layer     │   │  API Layer        │               │  │
│  │  │                  │   │                  │               │  │
│  │  │  OpenClaw Client │   │  REST /api/*     │               │  │
│  │  │  Tool Callbacks  │   │  WebSocket /ws   │               │  │
│  │  └──────────────────┘   └──────────────────┘               │  │
│  └─────────────────────────────────────────────────────────────┘  │
│         │              │                    │                      │
│         ▼              ▼                    ▼                      │
│  ┌────────────┐ ┌────────────┐   ┌──────────────────┐            │
│  │  OpenClaw   │ │  Laptop    │   │  Frontend          │            │
│  │  Gateway    │ │  Mic &     │   │  (SvelteKit :5173) │            │
│  │  (:18789)   │ │  Speaker   │   │                    │            │
│  │  + Claude   │ │            │   │                    │            │
│  └────────────┘ └────────────┘   └──────────────────┘            │
└───────────────────────────────────────────────────────────────────┘
         │ (WebSocket)                            │
         ▼                                        ▼ (HTTPS)
┌──────────────────┐                   ┌──────────────────┐
│  Anthropic API    │                   │  Gemini API       │
│  (Claude)         │                   │  (Google Cloud)   │
└──────────────────┘                   └──────────────────┘
```

---

## Data Flow: Complete Conversation Loop

```
1. Laptop mic captures audio continuously (16kHz, float32, 512-sample chunks)
   └─ backend/src/voice/pipeline.py — sounddevice.InputStream

2. Silero VAD detects speech start/end
   └─ backend/src/voice/vad.py — processes each chunk, fires speech_start/speech_end

3. On speech_end, accumulated audio buffer → MLX Whisper STT
   └─ backend/src/voice/stt.py — transcribes audio array to text string

4. Transcript text → OpenClaw WebSocket gateway
   └─ backend/src/bridge/openclaw.py — chat.send over ws://127.0.0.1:18789

5. OpenClaw → Claude Sonnet 4.5 (reasoning + tool calls)
   │
   ├──► Tool: "look_around" → POST /tools/vision/analyze
   │    └─ backend/src/bridge/tools.py → backend/src/vision/gemini.py
   │       Camera captures JPEG → base64 → Gemini API → text description
   │
   └──► Tool: "speak_to_user" → POST /tools/voice/speak
        └─ backend/src/bridge/tools.py → backend/src/voice/pipeline.py
           Text → Kokoro TTS → sounddevice.play → laptop speaker

6. Claude response streams back as deltas over WebSocket
   └─ backend/src/bridge/openclaw.py — on_delta callback fires per chunk

7. Deltas broadcast to frontend in real-time via /ws
   └─ backend/src/api/websocket.py — chat:delta events streamed to all clients
   └─ frontend/src/lib/stores/chatStore.ts — appends deltas to assistant message live

8. On stream completion, final text used for TTS
   └─ backend/src/bridge/openclaw.py — on_done callback fires with full text
   └─ backend/src/voice/pipeline.py — speak() method → Kokoro TTS → laptop speaker
```

### Text Chat Flow (Frontend WebSocket)

```
1. User types message in ChatPanel
   └─ frontend/src/lib/components/ChatPanel.svelte — form submit

2. Message sent over WebSocket as {"type": "chat", "data": "..."}
   └─ frontend/src/lib/stores/chatStore.ts — sendChat() via WS (REST fallback if disconnected)

3. Backend receives chat message on /ws endpoint
   └─ backend/src/api/websocket.py — forwards to openclaw_client.send_message_streaming()

4. OpenClaw processes and streams response deltas
   └─ backend/src/bridge/openclaw.py — chat.send over ws://127.0.0.1:18789

5. Each delta broadcast to frontend as chat:delta event
   └─ backend/src/api/websocket.py — _broadcast_delta() → all connected WS clients

6. Frontend appends deltas to assistant message in real-time (streaming cursor visible)
   └─ frontend/src/lib/stores/chatStore.ts — updateMessage() on each delta

7. On chat:done, streaming flag cleared, message finalized
   └─ frontend/src/lib/stores/chatStore.ts — marks message as complete
```

**Latency budget** (voice-to-voice): ~1.5–2s

- VAD detection: ~100ms
- Whisper STT: ~300ms
- Network + Claude reasoning: ~800ms
- Kokoro TTS: ~300ms

---

## File Map

### Backend (`backend/`)

| File             | Purpose                                                                                                                                                                                         |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pyproject.toml` | uv project config, all Python dependencies                                                                                                                                                      |
| `src/main.py`    | FastAPI app, async lifespan (connects OpenClaw WebSocket, starts voice pipeline), router registration, wires voice→OpenClaw→TTS loop                                                            |
| `src/config.py`  | `Settings` (pydantic-settings) — all env vars: `HUGO_OPENCLAW_URL`, `HUGO_OPENCLAW_TOKEN`, `HUGO_GEMINI_API_KEY`, model names, sample rate, VAD threshold, etc. Reads from `backend/.env` file. |

#### Voice (`backend/src/voice/`)

| File          | Purpose                                                                                                                                                                                                                                                                                                                           |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vad.py`      | `VoiceActivityDetector` — Silero VAD wrapper. Loads model via `torch.hub`, processes 512-sample chunks, detects speech_start/speech_end transitions. Singleton: `vad`.                                                                                                                                                            |
| `stt.py`      | `SpeechToText` — MLX Whisper wrapper via `mlx_audio.stt.generate.load_model`. Loads model, calls `model.generate(audio)` on numpy arrays, returns text. Singleton: `stt`. Model: `mlx-community/whisper-large-v3-turbo`.                                                                                                          |
| `tts.py`      | `TextToSpeech` — Kokoro TTS wrapper via `mlx_audio.tts.TTSPipeline`. Takes text, returns (audio_array, sample_rate). Singleton: `tts`. Model: `mlx-community/Kokoro-82M-bf16`, voice: `af_heart`.                                                                                                                                 |
| `pipeline.py` | `VoicePipeline` — Orchestrator. Opens `sounddevice.InputStream` (16kHz, mono, 512 blocksize). Audio callback runs VAD on each chunk, accumulates speech into buffer, on speech_end dispatches async STT + transcript callback. `speak()` method synthesizes text via TTS and plays through speakers. Singleton: `voice_pipeline`. |

**How voice pipeline starts**: `main.py` lifespan calls `voice_pipeline.start()`, which loads all three models (VAD, STT, TTS) and opens the mic stream. The `on_transcript` callback is set to send transcripts to OpenClaw and speak the response.

#### Vision (`backend/src/vision/`)

| File        | Purpose                                                                                                                                                                                                                                            |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `camera.py` | `Camera` — OpenCV `VideoCapture` wrapper. `capture_frame()` returns numpy BGR array. `capture_jpeg()` returns JPEG bytes. Singleton: `camera`.                                                                                                     |
| `gemini.py` | `GeminiVision` — Google GenAI client. `analyze(query)` captures a JPEG frame, base64-encodes it, sends to Gemini as inline image + text prompt, returns description string. Uses `google.genai.Client` with async API. Singleton: `gemini_vision`. |

**Vision is on-demand only** — triggered when Claude calls the `look_around` tool. No continuous streaming (saves cost/tokens).

#### Bridge (`backend/src/bridge/`)

| File          | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `openclaw.py` | `OpenClawClient` — WebSocket client using `websockets` library. Connects to OpenClaw gateway at `ws://127.0.0.1:18789` with protocol v3 handshake (challenge → connect → hello). `send_message(text)` sends `chat.send` requests, accumulates streamed `agent` event deltas, and resolves on `chat` `final` event. Background `_listen()` task handles all incoming frames. Auto-reconnects on first `send_message()` if disconnected. Auth via gateway token from `.env`. Singleton: `openclaw_client`. |
| `tools.py`    | FastAPI router mounted at `/tools`. Three endpoints that OpenClaw calls when Claude invokes tools: `POST /tools/vision/analyze` (camera + Gemini), `POST /tools/voice/speak` (TTS playback), `GET /tools/status` (health check).                                                                                                                                                                                                                                                                         |

**How OpenClaw integration works**: OpenClaw runs as a macOS LaunchAgent daemon (`openclaw gateway` on port 18789, auto-starts on boot). HUGO Backend connects via WebSocket and sends user messages using the `chat.send` method. OpenClaw forwards to Claude with the registered tool definitions (loaded from `openclaw-skills/` via `skills.load.extraDirs` in `~/.openclaw/openclaw.json`). When Claude calls a tool, OpenClaw POSTs back to HUGO Backend's `/tools/*` endpoints. The response streams back as `agent` delta events over the WebSocket connection.

#### API (`backend/src/api/`)

| File           | Purpose                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schemas.py`   | Pydantic models: `ChatRequest`, `ChatResponse`, `StatusResponse`, `WSMessage`.                                                                                                                                                                                                                                                                                                           |
| `routes.py`    | REST router at `/api`. `POST /api/chat` — text chat fallback (sends message to OpenClaw, returns response). `GET /api/status` — returns service health (voice, vision, openclaw).                                                                                                                                                                                                        |
| `websocket.py` | WebSocket endpoint at `/ws`. Maintains a set of connected clients. Accepts `chat` messages from the frontend and forwards them to OpenClaw via `send_message_streaming()`. Registers `on_delta`/`on_done` callbacks on the OpenClaw client to broadcast `chat:start`, `chat:delta`, and `chat:done` events to all connected frontend clients in real-time. Supports ping/pong keepalive. |

#### Tests (`backend/tests/`)

| File             | What it tests                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| `test_voice.py`  | VAD chunk processing, speech transitions, STT transcription, TTS synthesis — all with mocked models. |
| `test_vision.py` | Camera capture/JPEG encoding (mocked OpenCV), Gemini analysis (mocked API client).                   |
| `test_bridge.py` | OpenClaw client send/receive (mocked websockets), tool endpoint HTTP responses (FastAPI TestClient). |

### OpenClaw Skills (`openclaw-skills/hugo-tools/`)

| File           | Purpose                                                                                                                                                                                                                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SKILL.md`     | Tool definitions and behavior instructions for Claude. YAML frontmatter (`name`, `description`, `metadata` with `openclaw.emoji`) required for OpenClaw skill discovery. Defines `look_around` and `speak_to_user` tools with parameters and usage guidelines. Tells Claude to always speak responses aloud and use vision when asked about the environment. |
| `index.ts`     | Tool implementations. Each function makes an HTTP POST to HUGO Backend's `/tools/*` endpoints. `look_around` → `/tools/vision/analyze`, `speak_to_user` → `/tools/voice/speak`.                                                                                                                                                                              |
| `package.json` | Node.js package metadata for the skill.                                                                                                                                                                                                                                                                                                                      |

**Registering skills**: Add the `openclaw-skills/` directory to `skills.load.extraDirs` in `~/.openclaw/openclaw.json`. Skills require YAML frontmatter in `SKILL.md` with `name`, `description`, and `metadata` fields for OpenClaw to discover them. After updating, restart the gateway (`openclaw gateway restart`). Verify with `openclaw skills list` — the skill should appear with source `openclaw-extra`.

### Frontend (`frontend/`)

SvelteKit 5 + TypeScript + Tailwind CSS v4. Vite dev server proxies `/api`, `/tools`, `/ws` to the backend at localhost:8080.

| File                               | Purpose                                                                                |
| ---------------------------------- | -------------------------------------------------------------------------------------- |
| `vite.config.ts`                   | Tailwind v4 plugin, dev proxy config for backend.                                      |
| `src/app.css`                      | Tailwind import + CSS custom properties for dark theme colors.                         |
| `src/routes/+layout.svelte`        | App shell: header with title, StatusBar, settings link. Polls `/api/status` every 10s. |
| `src/routes/+page.svelte`          | Dashboard: 3-column grid with ChatPanel (2/3), VisionPanel + TranscriptLog (1/3).      |
| `src/routes/settings/+page.svelte` | Settings page: toggles for voice and vision.                                           |

#### Components (`frontend/src/lib/components/`)

| Component              | Purpose                                                                                                                                                                                             |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ChatPanel.svelte`     | Text chat interface. Input form at bottom, message list above with auto-scroll. Calls `sendChat()` from chatStore. Shows pulsing cursor during streaming, "Thinking..." before first delta arrives. |
| `StatusBar.svelte`     | Row of colored dots indicating service health (WS connection, voice, vision, OpenClaw). Reads from `statusStore`.                                                                                   |
| `VisionPanel.svelte`   | "Capture" button triggers `POST /tools/vision/analyze`. Displays Gemini's description text.                                                                                                         |
| `TranscriptLog.svelte` | Scrollable list of voice transcripts. Receives `transcripts` as a prop.                                                                                                                             |

#### Stores (`frontend/src/lib/stores/`)

| Store              | State                                                                   | Key functions                                                                                                                                                                                                                                                                                                           |
| ------------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `chatStore.ts`     | `messages: ChatMessage[]`, `isLoading: boolean`, `wsConnected: boolean` | `connectWs()` / `disconnectWs()` — manage WebSocket lifecycle with auto-reconnect. `sendChat(msg)` — sends via WebSocket (REST fallback). Handles `chat:start` (create placeholder), `chat:delta` (append text), `chat:done` (finalize), `chat:error` events. Maps OpenClaw `reqId` to local message IDs for streaming. |
| `statusStore.ts`   | `serviceStatus: ServiceStatus`, `connected: boolean`                    | `fetchStatus()` — GETs `/api/status`, updates store.                                                                                                                                                                                                                                                                    |
| `settingsStore.ts` | `voiceEnabled`, `visionEnabled` (writable booleans)                     | Simple toggles for frontend feature flags.                                                                                                                                                                                                                                                                              |

#### Types (`frontend/src/lib/types/index.ts`)

```typescript
ChatMessage { id, role, content, timestamp, streaming? }
ServiceStatus { voice, vision, openclaw }
WSMessage { type: 'transcript'|'response'|'status'|'error'|'pong'|'chat:start'|'chat:delta'|'chat:done'|'chat:error', data }
```

---

## Configuration

All backend configuration is via environment variables with `HUGO_` prefix (handled by pydantic-settings in `backend/src/config.py`):

| Variable              | Default                                | Purpose                                                                               |
| --------------------- | -------------------------------------- | ------------------------------------------------------------------------------------- |
| `HUGO_OPENCLAW_URL`   | `ws://127.0.0.1:18789`                 | OpenClaw gateway WebSocket address                                                    |
| `HUGO_OPENCLAW_TOKEN` | (empty)                                | OpenClaw gateway auth token (from `~/.openclaw/openclaw.json` → `gateway.auth.token`) |
| `HUGO_GEMINI_API_KEY` | (empty)                                | Google Gemini API key for vision                                                      |
| `HUGO_GEMINI_MODEL`   | `gemini-2.0-flash`                     | Gemini model name                                                                     |
| `HUGO_STT_MODEL`      | `mlx-community/whisper-large-v3-turbo` | MLX Whisper model ID                                                                  |
| `HUGO_TTS_MODEL`      | `mlx-community/Kokoro-82M-bf16`        | Kokoro TTS model ID                                                                   |
| `HUGO_TTS_VOICE`      | `af_heart`                             | Kokoro voice preset                                                                   |
| `HUGO_SAMPLE_RATE`    | `16000`                                | Audio sample rate (Hz)                                                                |
| `HUGO_VAD_THRESHOLD`  | `0.5`                                  | VAD speech detection threshold                                                        |
| `HUGO_BACKEND_URL`    | `http://localhost:8080`                | Self-URL for OpenClaw tool callbacks                                                  |
| `HUGO_CAMERA_INDEX`   | `0`                                    | OpenCV camera device index                                                            |
| `HUGO_HOST`           | `0.0.0.0`                              | Server bind host                                                                      |
| `HUGO_PORT`           | `8080`                                 | Server bind port                                                                      |

---

## Running

```bash
# Prerequisites
pnpm install                    # Root + frontend deps
cd backend && uv sync && cd ..  # Backend Python deps

# Set up .env (backend/.env)
HUGO_OPENCLAW_TOKEN=<your-gateway-token>  # from ~/.openclaw/openclaw.json → gateway.auth.token
HUGO_GEMINI_API_KEY=<your-key>            # optional, for vision

# OpenClaw runs as a macOS LaunchAgent (auto-starts on boot)
# To manually manage: openclaw gateway restart / openclaw health

# Run backend + frontend concurrently
pnpm dev

# Or separately:
pnpm dev:backend   # FastAPI on :8080
pnpm dev:frontend  # SvelteKit on :5173, proxies to backend
```

---

## Verification Checklist

1. `curl http://localhost:8080/tools/status` → `{"status":"ok","services":{...}}`
2. `curl -X POST http://localhost:8080/api/chat -H 'Content-Type: application/json' -d '{"message":"hello"}'` → Claude response
3. `curl -X POST http://localhost:8080/tools/vision/analyze -H 'Content-Type: application/json' -d '{"query":"What do you see?"}'` → Gemini description
4. Frontend at `http://localhost:5173` — chat works, status indicators show
5. `cd backend && uv run ruff check src/ tests/` → passes
6. `cd frontend && pnpm check` → 0 errors

---

## Phase 2: What's Next

Phase 2 adds robot integration (deferred from Phase 1):

- **Robot Controller** (`backend/src/robot/controller.py`) — Reachy Mini SDK wrapper for head/antenna/body movement
- **Robot tools** for OpenClaw — `move_head`, `play_emotion`, `dance`
- **Audio I/O via robot** — switch from laptop mic/speaker to Reachy Mini's mic/speaker using `mini.media.get_audio_sample()` / `push_audio_sample()`
- **Camera via robot** — switch from laptop camera to Reachy Mini's camera using `mini.media.get_frame()`
- **Speech-reactive movement** — head wobble and antenna animations during speech
- **Integration plugins** — calendar, email, notes (OpenClaw tools)

The architecture is designed for this: the voice pipeline's `sounddevice` I/O and the camera's `cv2.VideoCapture` can be swapped for Reachy Mini SDK calls without changing the rest of the pipeline.

---

## Design Decisions

### Why modular MLX-Audio instead of Moshi MLX?

Moshi is a full-duplex speech-to-speech model that does its own reasoning internally. There's no way to extract just the transcript or feed it text for vocalization — it's all-in-one. Since HUGO routes reasoning through Claude (via OpenClaw), we need a clean STT/TTS layer. The modular pipeline (Silero VAD + MLX Whisper + Kokoro) gives full control over each stage.

### Why OpenClaw as orchestrator (Approach A)?

OpenClaw manages conversation context, tool execution, memory, and multi-turn reasoning. Reimplementing this in HUGO Backend would be unnecessary duplication. HUGO Backend is a hardware bridge that exposes capabilities as HTTP tool endpoints that OpenClaw calls.

### Why on-demand vision instead of continuous streaming?

Continuous 1 FPS Gemini streaming costs ~$0.03/min and accumulates tokens. On-demand (triggered by Claude's `look_around` tool call) is cheaper and only fires when context requires it.

### Why singletons for services?

Each service (vad, stt, tts, camera, gemini_vision, openclaw_client, voice_pipeline) is a module-level singleton. This avoids re-loading ML models and keeps state centralized. The FastAPI lifespan manages startup/shutdown.

---

## Sources

- `thoughts/shared/research/openclaw-research.md` — OpenClaw platform docs, API, integration strategy
- `thoughts/shared/research/reachy-mini-research.md` — Robot SDK, hardware specs, safety limits
- `thoughts/shared/research/voice-vision-research.md` — MLX-Audio, Gemini API, voice tech evaluation
