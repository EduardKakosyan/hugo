# HUGO — Personal Assistant Agent for Reachy Mini

A personal assistant agent powered by the Reachy Mini robot SDK. Features real-time voice conversation, vision processing, multi-provider LLM reasoning, and extensible API integrations — all controlled through a SvelteKit web dashboard.

## Architecture

```
User ↔ Frontend (SvelteKit 5) ↔ Backend (FastAPI) ↔ Reachy Mini SDK ↔ Robot/Simulator
                                       ↕
                                 LiteLLM (multi-provider)
                                 Voice Engine (PersonaPlex / Cloud)
                                 Integration Plugins (Outlook, Calendar, Obsidian)
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+ and pnpm
- Reachy Mini SDK (`pip install reachy-mini`)

### Backend

```bash
cd backend
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8080
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### Robot Simulator

```bash
reachy-mini-daemon --sim
```

## Features

- **Multi-provider LLM**: Switch between Gemini, GPT-4o, Claude, Mistral, or local Ollama models
- **Voice I/O**: NVIDIA PersonaPlex for speech-to-speech, with OpenAI Whisper/TTS fallback
- **Vision**: Live camera stream + multimodal scene analysis
- **Integration plugins**: Outlook email, Google Calendar, Obsidian notes
- **Web dashboard**: Real-time telemetry, video feed, chat interface, settings management

## Development

```bash
# Backend linting & testing
cd backend && ruff check src/ tests/ && mypy src/ && pytest

# Frontend linting & testing
cd frontend && pnpm lint && pnpm test
```

## Project Structure

```
HUGO/
├── backend/          # Python FastAPI application
│   ├── src/
│   │   ├── main.py           # App entry point
│   │   ├── config.py         # Settings
│   │   ├── robot/            # SDK wrapper
│   │   ├── agent/            # LLM orchestrator
│   │   ├── voice/            # Voice engines
│   │   ├── vision/           # Camera & analysis
│   │   ├── integrations/     # Plugin system
│   │   └── api/              # REST + WebSocket
│   └── tests/
├── frontend/         # SvelteKit 5 dashboard
│   └── src/
│       ├── routes/           # Pages
│       └── lib/              # Components, stores, types
├── .github/          # CI workflows
├── .claude/          # AI agent commands
└── .husky/           # Git hooks
```

## License

MIT
