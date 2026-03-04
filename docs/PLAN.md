# HUGO — Ground Plan

> **Helpful Universal Guide & Organizer**
> A voice-first AI agent platform built in Go, designed to orchestrate tools,
> control a Reachy Mini robot, and communicate primarily through speech.

**Status:** Pre-implementation — scaffolding phase
**Last updated:** 2026-02-26

---

## 1. Vision

HUGO is a conversational AI agent that:
- Communicates via **voice** (STT → Agent → TTS) as the primary interface
- Runs on the **tRPC-agent-go** framework for agent orchestration
- Controls a **Reachy Mini** robot via HTTP/WebSocket
- Supports **tools** that can be called by the agent during conversation
- Can optionally process **video** (toggled by voice command)
- Exposes a **WebSocket API** for frontend/external clients

The user speaks to HUGO. HUGO listens, thinks, uses tools if needed, and speaks back.
Eventually HUGO also sees through the robot's camera when asked.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTS                              │
│  Browser (WebSocket)  │  CLI  │  Mobile  │  Voice Direct    │
└────────────┬────────────────────────────────────────────────┘
             │ WebSocket / HTTP
             ▼
┌─────────────────────────────────────────────────────────────┐
│                     GO SERVER (cmd/hugo)                     │
│                                                             │
│  ┌──────────────┐   ┌──────────────────────────────────┐   │
│  │  HTTP/WS     │   │     VOICE PIPELINE               │   │
│  │  Server      │──▶│  Mic → VAD → STT → [text]        │   │
│  │  (gorilla)   │   │                                    │   │
│  └──────────────┘   │  Speech Queue ← [text chunks]     │   │
│                     │  Speech Queue → TTS → Speaker/WS   │   │
│                     └──────────┬──────────▲──────────────┘   │
│                                │           │                 │
│                         transcript    speak/announce         │
│                                │           │                 │
│                                ▼           │                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              EVENT CONSUMER (goroutine)               │   │
│  │  Reads <-chan *event.Event from runner, decides what  │   │
│  │  to speak: text chunks, tool announcements, results.  │   │
│  │  Runs CONCURRENTLY with the agent — never blocks it.  │   │
│  └──────────────────────────┬───────────────────────────┘   │
│                             │ events                        │
│                             │                               │
│  ┌──────────────────────────┴───────────────────────────┐   │
│  │              tRPC-AGENT-GO RUNNER                      │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────┐     │   │
│  │  │           HUGO LLMAgent (root)               │     │   │
│  │  │  - System instruction                        │     │   │
│  │  │  - Tool dispatch                             │     │   │
│  │  │  - Session memory                            │     │   │
│  │  │  - Streaming response via <-chan *event.Event │     │   │
│  │  └──────────────┬──────────────────────────────┘     │   │
│  │                 │ tool calls                          │   │
│  │                 ▼                                     │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │            TOOL REGISTRY                      │    │   │
│  │  │  - Reachy Mini control tools                  │    │   │
│  │  │  - Vision tool (camera capture + VLM)         │    │   │
│  │  │  - Web search / fetch tools                   │    │   │
│  │  │  - MCP tool bridge (future)                   │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          REACHY MINI CLIENT                           │   │
│  │  HTTP client  → REST API (daemon :8000)               │   │
│  │  WS client    → state stream, target stream           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Concurrency Model: Live Voice Feedback

The core UX principle of HUGO: **the agent talks to you while it works, not
after it's done.** This is possible because the agent runner and the voice
pipeline run on separate goroutines, connected by a channel.

### The Problem with Request-Response Voice

Most voice assistants work like this:
```
You speak → agent thinks (silence...) → agent done → speaks entire answer
```

For quick questions this is fine. But for multi-step tasks ("update my calendar,
then find flights, then book the cheapest one") the user sits in silence for
30+ seconds. Bad UX.

### HUGO's Approach: Concurrent Event Consumer

The tRPC-agent-go runner emits events on a `<-chan *event.Event` as the agent
works. A separate **event consumer goroutine** reads these events and feeds
text to the voice pipeline's speech queue. The agent never pauses to wait for
TTS — it keeps working.

```
    RUNNER GOROUTINE                    EVENT CONSUMER GOROUTINE
    ────────────────                    ────────────────────────
    │                                   │
    ├─ LLM decides: call calendar  ───▶ speak "Updating your calendar..."
    ├─ execute calendar tool            │ (speaking concurrently)
    │  (HTTP call, 2 seconds)           │ (TTS playing audio)
    ├─ tool returns success        ───▶ speak "Calendar's done."
    ├─ LLM decides: call flights   ───▶ speak "Now searching for flights."
    ├─ execute flights tool             │ (speaking concurrently)
    │  (API call, 5 seconds)            │ (TTS playing audio)
    ├─ tool returns results        ───▶ speak "Found a $450 flight on ANA."
    ├─ LLM generates question      ───▶ speak "Want me to book it?"
    └─ (waits for next input)           └─ (listening for speech)
```

### Three Types of Speakable Events

The event consumer categorizes each event and decides what to speak:

| Event Type | What the Consumer Does | Example Speech |
|---|---|---|
| **Text chunk** (streaming tokens) | Buffers tokens, speaks at sentence boundaries | "The weather today is sunny." |
| **Tool call** (agent invokes a tool) | Announces what's happening | "Let me check your calendar..." |
| **Tool result** (tool returns) | Summarizes the result naturally | "Done — your meeting is moved to 3 PM." |

Not every event needs to be spoken. The consumer applies rules:
- Skip tool calls for fast tools (< 1 second) — just speak the result
- Announce slow tools (API calls, searches) so the user knows something is happening
- Never speak raw JSON — summarize tool results in natural language

### Speech Queue (Non-Blocking TTS)

The voice pipeline maintains a **speech queue** — an internal channel of text
segments waiting to be synthesized and played. `Speak()` enqueues and returns
immediately. A dedicated TTS goroutine drains the queue.

```
Event Consumer ──Speak("Updating calendar...")──▶ ┌─────────────┐
Event Consumer ──Speak("Calendar's done.")─────▶ │ Speech Queue │ ──▶ TTS ──▶ Speaker
Event Consumer ──Speak("Searching flights...")──▶ │  (buffered   │
                                                  │   channel)   │
                                                  └─────────────┘
```

This means:
- The agent runner never blocks on TTS. It keeps calling tools.
- The event consumer never blocks on TTS. It keeps processing events.
- Speech plays in order, with natural pacing.
- If the user interrupts (barge-in), we cancel the runner context AND drain the queue.

### Barge-In: Cancelling Mid-Task

When the user starts speaking while HUGO is both talking AND working:

```go
// Per-task context — cancelled on barge-in
taskCtx, taskCancel := context.WithCancel(sessionCtx)

// VAD detects user speech while HUGO is active
go func() {
    for transcript := range voicePipeline.Transcripts() {
        // Cancel the current task (stops runner + drains speech queue)
        taskCancel()
        voicePipeline.DrainQueue()

        // Start new task with fresh context
        taskCtx, taskCancel = context.WithCancel(sessionCtx)
        go processUserInput(taskCtx, transcript, runner, voicePipeline)
    }
}()
```

The `taskCtx` cancellation propagates through:
1. The runner's `Run()` call — stops the LLM and any in-flight tool calls
2. The event consumer — stops reading and exits
3. The speech queue — drains unsaid segments
4. Any HTTP calls to Reachy Mini or external APIs — cancelled via context

### Code Shape (Pseudocode)

```go
// internal/voice/consumer.go

// ConsumeEvents reads agent events and feeds the speech queue.
// Runs on its own goroutine. Returns when the event channel closes
// or ctx is cancelled.
func ConsumeEvents(
    ctx       context.Context,
    events    <-chan *event.Event,
    pipeline  voice.Pipeline,
    announcer EventAnnouncer,    // decides what to say for each event type
) {
    var sentence strings.Builder

    for {
        select {
        case <-ctx.Done():
            return
        case evt, ok := <-events:
            if !ok {
                // Channel closed — agent finished. Flush remaining text.
                if sentence.Len() > 0 {
                    pipeline.Enqueue(ctx, sentence.String())
                }
                return
            }

            // Tool call: optionally announce it
            if tc := extractToolCall(evt); tc != nil {
                if ann := announcer.AnnounceToolCall(tc); ann != "" {
                    // Flush any buffered sentence first
                    if sentence.Len() > 0 {
                        pipeline.Enqueue(ctx, sentence.String())
                        sentence.Reset()
                    }
                    pipeline.Enqueue(ctx, ann)
                }
                continue
            }

            // Tool result: optionally summarize it
            if tr := extractToolResult(evt); tr != nil {
                if ann := announcer.AnnounceToolResult(tr); ann != "" {
                    pipeline.Enqueue(ctx, ann)
                }
                continue
            }

            // Text token: buffer and speak at sentence boundaries
            if text := extractText(evt); text != "" {
                sentence.WriteString(text)
                if isSentenceBoundary(sentence.String()) {
                    pipeline.Enqueue(ctx, sentence.String())
                    sentence.Reset()
                }
            }
        }
    }
}
```

### EventAnnouncer Interface

```go
// internal/voice/announcer.go

// EventAnnouncer decides what the voice should say for tool events.
// Returns empty string to skip speaking.
type EventAnnouncer interface {
    // AnnounceToolCall returns speech text when a tool starts.
    // Example: "Looking that up for you..."
    AnnounceToolCall(tc *ToolCallInfo) string

    // AnnounceToolResult returns speech text when a tool completes.
    // Example: "Got it — your meeting is at 3 PM."
    AnnounceToolResult(tr *ToolResultInfo) string
}
```

The default announcer maps tool names to natural phrases:
```go
// Example rules (configurable):
// "current_time"  → skip announcement (fast tool, just let the LLM speak the result)
// "search_web"    → "Let me search for that..."
// "update_calendar" → "Updating your calendar..."
// "look_at"       → skip (robot movement is visible, no need to narrate)
// "capture_image" → "Let me take a look..."
```

---

## 4. Technology Decisions

### 4.1 Agent Framework: tRPC-agent-go

**Why:** Most complete Go agent framework available (v1.6.0, 921+ stars, Tencent production-grade).

Key features we use:
- **LLMAgent** — ReAct loop with tool calling, streaming via `<-chan *event.Event`
- **Runner** — session management, event persistence, plugin hooks
- **Function tools** — generic `NewFunctionTool[I, O]` with auto JSON schema
- **MCP toolsets** — stdio/HTTP/SSE for external tool servers (future)
- **Session backends** — inmemory for dev, Redis/Postgres for production
- **AG-UI server** — built-in SSE endpoint (optional, for web frontend)
- **Model providers** — OpenAI, Anthropic, Gemini built in

Import path: `trpc.group/trpc-go/trpc-agent-go`

### 4.2 LLM Provider: Anthropic Claude (primary)

- Model: Claude Sonnet 4 / Opus 4 via tRPC-agent-go's anthropic provider
- Fallback: OpenAI GPT-4o, Gemini 2.5 Flash (all supported by framework)
- Configured per-agent, swappable at runtime

### 4.3 Voice Pipeline (Phase 4)

| Stage | Technology | Notes |
|---|---|---|
| Audio capture | `gen2brain/malgo` (miniaudio) | Cross-platform, 16kHz mono |
| VAD | `plandem/silero-go` (Silero via ONNX) | 87% TPR, best accuracy |
| STT | `whisper.cpp` Go bindings (local) or OpenAI Whisper API (cloud) | Local for low latency, cloud as fallback |
| TTS | OpenAI TTS API or ElevenLabs (`haguro/elevenlabs-go`) | Streaming via `io.Pipe` |

Pipeline architecture: goroutine-per-stage connected by channels, managed by `errgroup`.

### 4.4 Reachy Mini Control

- No Go SDK exists — we build a thin client
- REST API at `http://reachy-mini.local:8000/api/`
- WebSocket for state streaming and continuous target updates
- OpenAPI spec available at `/openapi.json` — use `oapi-codegen` to generate types
- Each robot action registered as a tRPC-agent-go function tool

### 4.5 Vision (Phase 6)

- Camera: MJPEG stream from Reachy Mini at `/api/camera/stream`
- VLM: Cloud API (Gemini, Claude vision) — send frame + prompt, get description
- Activated as a toggleable tool the agent can call when asked

---

## 5. Directory Structure

```
HUGO/
├── cmd/
│   └── hugo/
│       └── main.go              # Entry point — wires everything together
├── internal/
│   ├── agent/
│   │   ├── hugo.go              # Root LLMAgent definition + system prompt
│   │   ├── config.go            # Runner, session, model configuration
│   │   └── tools.go             # Tool registration (wires tools to agent)
│   ├── server/
│   │   ├── server.go            # HTTP + WebSocket server
│   │   └── handlers.go          # WS message handling, voice relay
│   ├── voice/
│   │   ├── pipeline.go          # Goroutine pipeline orchestrator (Enqueue/DrainQueue)
│   │   ├── queue.go             # Speech queue — buffered chan + TTS drain goroutine
│   │   ├── consumer.go          # Event consumer — reads agent events, feeds queue
│   │   ├── announcer.go         # EventAnnouncer — tool name → spoken phrase mapping
│   │   ├── vad.go               # VAD interface + Silero implementation
│   │   ├── stt.go               # STT interface + implementations
│   │   └── tts.go               # TTS interface + implementations
│   ├── robot/
│   │   ├── client.go            # Reachy Mini HTTP + WS client
│   │   ├── types.go             # Request/response structs (or generated)
│   │   └── tools.go             # Robot actions as agent function tools
│   └── vision/
│       ├── capture.go           # Camera frame grabber (MJPEG)
│       └── tools.go             # Vision tool (capture + VLM query)
├── docs/
│   └── PLAN.md                  # This file
├── go.mod
├── go.sum
├── .env.example                 # Required env vars template
├── .gitignore
└── README.md
```

### Conventions

- **`cmd/`** — main packages only. Thin: parse config, wire dependencies, start server.
- **`internal/`** — all application logic. Not importable by external packages.
- **Interfaces defined where consumed**, not where implemented (Go convention).
- **One package per concern** — `agent`, `server`, `voice`, `robot`, `vision`.
- **No `pkg/` directory** — everything is internal to this application.
- **Tools are registered in `internal/agent/tools.go`** — single place to see all capabilities.

---

## 6. Key Interfaces

These interfaces define the boundaries between packages. Implementations live in their respective packages.

### 6.1 Voice Pipeline Interfaces

```go
// internal/voice/pipeline.go

// Pipeline orchestrates VAD → STT on the input side, and a speech queue →
// TTS → playback on the output side. Input and output are independent —
// the agent can enqueue speech while still listening for barge-in.
type Pipeline interface {
    // Start begins listening. Transcripts arrive on the returned channel.
    Start(ctx context.Context) (<-chan Transcript, error)

    // Enqueue adds text to the speech queue. Returns immediately (non-blocking).
    // A background goroutine drains the queue through TTS → playback in order.
    Enqueue(ctx context.Context, text string) error

    // DrainQueue discards all queued speech that hasn't started playing yet.
    // Used on barge-in to stop HUGO from speaking stale segments.
    DrainQueue()

    // Interrupt cancels the currently-playing TTS audio AND drains the queue.
    // Full barge-in: stop talking immediately and throw away pending speech.
    Interrupt()

    // IsSpeaking returns true if audio is currently playing or the queue is non-empty.
    IsSpeaking() bool

    // Close shuts down all pipeline goroutines.
    Close() error
}

type Transcript struct {
    Text      string
    Timestamp time.Time
}
```

### 6.2 Robot Client Interface

```go
// internal/robot/client.go

// Client controls a Reachy Mini via its daemon API.
type Client interface {
    // Movement
    Goto(ctx context.Context, req GotoRequest) error
    SetTarget(ctx context.Context, target FullBodyTarget) error
    PlayMove(ctx context.Context, dataset, name string) error
    StopMove(ctx context.Context, moveID string) error

    // State
    GetState(ctx context.Context) (*FullState, error)
    StreamState(ctx context.Context) (<-chan FullState, error)

    // Motors
    EnableMotors(ctx context.Context) error
    DisableMotors(ctx context.Context) error

    // Lifecycle
    WakeUp(ctx context.Context) error
    Sleep(ctx context.Context) error

    // Camera
    CaptureFrame(ctx context.Context) ([]byte, error) // JPEG frame

    Close() error
}
```

### 6.3 Vision Interface

```go
// internal/vision/tools.go

// Analyzer sends an image frame to a VLM and returns a description.
type Analyzer interface {
    Analyze(ctx context.Context, frame []byte, prompt string) (string, error)
}
```

---

## 7. Implementation Phases

Each phase is a buildable, testable increment. No phase depends on hardware
unless noted. Phases 1-3 can be developed and tested with just a terminal.

### Phase 1: Hello Agent

**Goal:** Go module + tRPC-agent-go + basic text chat in the terminal.

**What you'll learn:** Go modules, packages, interfaces, struct methods, error handling.

Tasks:
1. `go mod init github.com/eduardkakosyan/hugo`
2. Add tRPC-agent-go dependency
3. Create `cmd/hugo/main.go` — initialize model, agent, runner
4. Create `internal/agent/hugo.go` — define root LLMAgent with system prompt
5. Create `internal/agent/config.go` — model + session + runner factory
6. Wire a CLI conversation loop: stdin → runner.Run() → stdout
7. Test: have a multi-turn conversation in the terminal

**Deliverable:** `go run ./cmd/hugo` starts an interactive text chat.

**Key tRPC-agent-go patterns:**
```go
// Create model
model := openai.New("claude-sonnet-4-20250514",
    openai.WithBaseURL("https://api.anthropic.com/v1"),
    openai.WithVariant("anthropic"),
)

// Create agent
agent := llmagent.New("hugo",
    llmagent.WithModel(model),
    llmagent.WithInstruction("You are HUGO..."),
    llmagent.WithGenerationConfig(model.GenerationConfig{Stream: true}),
)

// Create runner
r := runner.NewRunner("hugo", agent,
    runner.WithSessionService(inmemory.NewService()),
)

// Run conversation
events, _ := r.Run(ctx, userID, sessionID, msg)
for evt := range events {
    // print streaming text
}
```

### Phase 2: Add Tools

**Goal:** Register custom function tools the agent can call.

**What you'll learn:** Go generics, JSON struct tags, the tool interface pattern.

Tasks:
1. Create `internal/agent/tools.go`
2. Define 2-3 example tools as `function.NewFunctionTool[I, O]`:
   - A simple utility (e.g., current time, calculator)
   - A stub robot tool (returns mock data, no real robot needed)
3. Register tools with the agent via `llmagent.WithTools()`
4. Test: ask the agent questions that require tool use

**Deliverable:** Agent correctly calls tools and incorporates results.

**Key pattern:**
```go
type TimeArgs struct{}
type TimeResult struct {
    Time string `json:"time"`
}

timeTool := function.NewFunctionTool(
    func(ctx context.Context, args TimeArgs) (TimeResult, error) {
        return TimeResult{Time: time.Now().Format(time.RFC1123)}, nil
    },
    function.WithName("current_time"),
    function.WithDescription("Returns the current date and time"),
)
```

### Phase 3: WebSocket Server

**Goal:** HTTP server with WebSocket endpoint for text chat.

**What you'll learn:** `net/http`, gorilla/websocket, concurrent connection handling.

Tasks:
1. Create `internal/server/server.go` — HTTP server with WS upgrade
2. Create `internal/server/handlers.go` — WS message protocol (JSON)
3. Wire: WS text message → runner.Run() → stream events back over WS
4. Keep the CLI mode as an alternative entry point
5. Test: connect from a WebSocket client (websocat, Postman, browser console)

**Message protocol (JSON over WebSocket):**
```json
// Client → Server
{"type": "message", "text": "What time is it?"}

// Server → Client (streaming)
{"type": "chunk", "text": "The current"}
{"type": "chunk", "text": " time is"}
{"type": "chunk", "text": " 3:45 PM."}
{"type": "done"}

// Server → Client (tool use notification)
{"type": "tool_call", "tool": "current_time", "args": {}}
{"type": "tool_result", "tool": "current_time", "result": {"time": "..."}}
```

**Deliverable:** `go run ./cmd/hugo serve` starts an HTTP server with WS chat.

### Phase 4: Voice Pipeline

**Goal:** Full voice loop with live feedback — HUGO talks to you while it works.

**What you'll learn:** Goroutines, channels, errgroup, context cancellation, audio I/O,
the concurrent event consumer pattern (see Section 3).

Tasks:
1. Create `internal/voice/vad.go` — VAD interface + Silero implementation
2. Create `internal/voice/stt.go` — STT interface + Whisper API implementation
3. Create `internal/voice/tts.go` — TTS interface + OpenAI TTS implementation
4. Create `internal/voice/queue.go` — speech queue (buffered channel + TTS drain goroutine)
5. Create `internal/voice/pipeline.go` — goroutine orchestrator with `Enqueue()` / `DrainQueue()`
6. Create `internal/voice/consumer.go` — event consumer (reads agent events, feeds speech queue)
7. Create `internal/voice/announcer.go` — `EventAnnouncer` with default tool→phrase mappings
8. Wire the main voice loop:
   - VAD → STT → transcript channel
   - Transcript → runner.Run() → event channel
   - Event channel → ConsumeEvents() → speech queue → TTS → playback
   - All three run concurrently via goroutines
9. Implement barge-in:
   - VAD detects speech while HUGO is speaking → cancel task context
   - Task context cancellation stops runner, consumer, and drains queue
   - New task starts with fresh context
10. Test: multi-step tool task with voice — verify HUGO speaks progress updates

**Main voice loop wiring:**
```go
transcripts, _ := voicePipeline.Start(ctx)

var taskCancel context.CancelFunc

for transcript := range transcripts {
    // Barge-in: cancel any in-progress task
    if taskCancel != nil {
        taskCancel()
        voicePipeline.Interrupt()
    }

    taskCtx, cancel := context.WithCancel(ctx)
    taskCancel = cancel

    go func(t Transcript) {
        defer cancel()

        // Agent works on its own goroutine
        events, err := runner.Run(taskCtx, userID, sessionID, textMessage(t.Text))
        if err != nil {
            voicePipeline.Enqueue(taskCtx, "Sorry, something went wrong.")
            return
        }

        // Event consumer speaks progress on its own goroutine
        // (see Section 3 for ConsumeEvents implementation)
        ConsumeEvents(taskCtx, events, voicePipeline, defaultAnnouncer)
    }(transcript)
}
```

**Goroutine layout during a multi-step task:**
```
goroutine 1: VAD → STT → transcript channel (always running, listening for barge-in)
goroutine 2: runner.Run() — agent thinking + tool execution (per-task, cancellable)
goroutine 3: ConsumeEvents() — reads events, enqueues speech (per-task, cancellable)
goroutine 4: speech queue drain → TTS → playback (always running, plays in order)
```

**Deliverable:** `go run ./cmd/hugo voice` starts a voice conversation where HUGO
gives live progress updates during multi-step tasks and can be interrupted mid-sentence.

### Phase 5: Reachy Mini Integration

**Goal:** Agent can control the robot through tool calls.

**Requires:** Access to a Reachy Mini (or mock server for testing).

Tasks:
1. Create `internal/robot/types.go` — request/response structs from OpenAPI spec
2. Create `internal/robot/client.go` — HTTP + WS client implementing `Client` interface
3. Create `internal/robot/tools.go` — wrap client methods as agent function tools:
   - `look_at` — move head to face a direction
   - `express_emotion` — play predefined emotion animations
   - `nod` / `shake_head` — quick gesture moves
   - `wake_up` / `go_to_sleep` — lifecycle
4. Register robot tools with the agent
5. Test: "HUGO, look left" → agent calls `look_at` → robot moves

**Tool example:**
```go
type LookAtArgs struct {
    Direction string `json:"direction" description:"left, right, up, down, or at_speaker"`
}

lookAtTool := function.NewFunctionTool(
    func(ctx context.Context, args LookAtArgs) (map[string]string, error) {
        target := directionToTarget(args.Direction)
        err := robotClient.Goto(ctx, GotoRequest{
            Head:     &target,
            Duration: 0.8,
            Interpolation: "minjerk",
        })
        return map[string]string{"status": "done"}, err
    },
    function.WithName("look_at"),
    function.WithDescription("Move the robot's head to look in a direction"),
)
```

**Deliverable:** Agent controls robot head, antennas, body via voice commands.

### Phase 6: Vision

**Goal:** Agent can see through the robot's camera when asked.

Tasks:
1. Create `internal/vision/capture.go` — grab JPEG frame from MJPEG stream
2. Create `internal/vision/tools.go` — vision tool that captures + queries VLM
3. Register as a tool: "What do you see?" → capture frame → send to Claude/Gemini vision → describe
4. Toggle: agent decides when to use vision based on conversation context

**Deliverable:** "HUGO, what's in front of you?" → agent describes the scene.

---

## 8. Configuration

All configuration via environment variables (loaded from `.env` in dev):

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-...       # Primary model provider
OPENAI_API_KEY=sk-...              # Fallback + TTS + STT
GOOGLE_API_KEY=...                 # Gemini (optional)

# Agent
HUGO_MODEL=claude-sonnet-4-20250514   # Default model
HUGO_MAX_TOOLS_PER_TURN=5             # Safety limit

# Voice
HUGO_STT_PROVIDER=whisper-api         # whisper-api | whisper-local | google-cloud
HUGO_TTS_PROVIDER=openai              # openai | elevenlabs
HUGO_VAD_THRESHOLD=0.5                # Silero VAD sensitivity

# Robot
REACHY_MINI_HOST=reachy-mini.local    # Daemon hostname
REACHY_MINI_PORT=8000                 # Daemon port

# Server
HUGO_PORT=8080                        # HTTP server port
HUGO_SESSION_BACKEND=inmemory         # inmemory | redis | postgres
```

---

## 9. Testing Strategy

- **Unit tests** for each package (`go test ./internal/...`)
- **Mock interfaces** — robot client, voice pipeline, STT/TTS providers all behind interfaces for easy mocking
- **Integration tests** tagged with `//go:build integration` — require real API keys or hardware
- **Manual testing** via CLI mode (Phase 1) and WebSocket (Phase 3)

---

## 10. Development Commands

```bash
# Run (text chat mode)
go run ./cmd/hugo

# Run (HTTP server mode)
go run ./cmd/hugo serve

# Run (voice mode)
go run ./cmd/hugo voice

# Test
go test ./...

# Lint
golangci-lint run

# Build
go build -o bin/hugo ./cmd/hugo
```

---

## 11. Dependencies (Expected)

```
trpc.group/trpc-go/trpc-agent-go    # Agent framework
github.com/gorilla/websocket         # WebSocket server
github.com/joho/godotenv             # .env loading
github.com/plandem/silero-go         # VAD (Phase 4)
github.com/ggerganov/whisper.cpp     # Local STT (Phase 4, optional)
github.com/sashabaranov/go-openai    # OpenAI API (STT + TTS)
github.com/haguro/elevenlabs-go      # ElevenLabs TTS (optional)
github.com/gen2brain/malgo           # Audio capture (Phase 4)
golang.org/x/sync                    # errgroup for pipeline
```

---

## 12. Agent System Prompt (Draft)

```
You are HUGO (Helpful Universal Guide & Organizer), a conversational AI agent
embodied in a Reachy Mini robot.

You communicate primarily through voice. Keep responses concise and natural —
you are speaking, not writing an essay. Aim for 1-3 sentences unless the user
asks for detail.

IMPORTANT — LIVE PROGRESS: When performing multi-step tasks, give brief spoken
updates between tool calls so the user knows what's happening. Don't go silent
for long stretches. Examples:
- "Got it, updating your calendar now." (before calling update_calendar)
- "That's done. Let me search for flights next." (after calendar, before flights)
- "Found some options — the cheapest is $450 on ANA." (after flights return)
Keep progress updates to ONE short sentence. Don't narrate every detail.

You have access to tools for:
- Controlling your robot body (head movement, expressions, gestures)
- Checking the current time and date
- Searching the web for information
- Looking through your camera to see the world (when asked)

When you use a robot tool, describe what you're doing naturally:
"Let me look over there" (while calling look_at)
"Sure, I'll nod" (while calling nod)

If you don't have a tool for something, say so honestly.
Never make up information — use your search tool if unsure.
```

---

## 13. Open Questions

These should be resolved as we build:

1. **Session persistence** — inmemory is fine for dev, but what backend for production? Redis vs Postgres?
2. **Multi-user** — single user for now, but the architecture should not prevent multi-user later.
3. **MCP tools** — should we expose HUGO's tools as an MCP server, connect to external MCP servers, or both?
4. **Frontend** — SvelteKit (matching old HUGO), React, or just the tRPC AG-UI built-in web UI?
5. **Deployment** — single binary on the Reachy Mini's Raspberry Pi? Or separate server + robot?
6. **Wake word** — should HUGO listen continuously or require a button/wake word to activate?

---

## 14. References

- [tRPC-agent-go documentation](https://trpc-group.github.io/trpc-agent-go/)
- [tRPC-agent-go GitHub](https://github.com/trpc-group/trpc-agent-go)
- [Google ADK-Go](https://github.com/google/adk-go) — reference architecture
- [Reachy Mini SDK](https://github.com/pollen-robotics/reachy_mini) — Python SDK, API reference
- [Reachy Mini daemon API](http://reachy-mini.local:8000/docs) — Swagger UI (requires running daemon)
- [PicoClaw](https://github.com/sipeed/picoclaw) — lightweight Go agent reference
- [lokutor-orchestrator](https://github.com/lokutor-ai/lokutor-orchestrator) — Go voice pipeline reference
- [Go Concurrency Patterns: Pipelines](https://go.dev/blog/pipelines)
