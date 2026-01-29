# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HUGO is a personal assistant agent for the Reachy Mini robot. It is a monorepo with two workspaces:

- **`backend/`** — Python FastAPI application providing robot control, multi-provider LLM reasoning, voice I/O, vision processing, and an extensible integration plugin system.
- **`frontend/`** — SvelteKit 5 web dashboard for live video, chat, telemetry, and configuration.

## Architecture

```
User ↔ Frontend (SvelteKit) ↔ Backend (FastAPI) ↔ Reachy Mini SDK ↔ Robot/Simulator
                                    ↕
                              LiteLLM (multi-provider LLM)
                              Voice Engine (PersonaPlex / Cloud)
                              Integration Plugins (Outlook, Calendar, Obsidian)
```

## Commands

```bash
# Frontend (pnpm)
cd frontend && pnpm install
cd frontend && pnpm dev           # Dev server on :5173
cd frontend && pnpm build         # Production build
cd frontend && pnpm lint          # ESLint + Prettier
cd frontend && pnpm test          # Vitest

# Backend (Python 3.12+, uv)
cd backend && uv sync --dev       # Install dependencies
cd backend && uv run uvicorn src.main:app --reload --port 8080
cd backend && uv run ruff check src/ tests/
cd backend && uv run mypy src/
cd backend && uv run pytest

# Robot simulator
reachy-mini-daemon --sim
```

## Git Workflow

**Commit Message Format (enforced by commitlint):**

- Format: `type: description` (lowercase, max 100 chars)
- Types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `ci`, `perf`

**Before Committing:**

1. Backend: `ruff check`, `mypy`, `pytest`
2. Frontend: `pnpm lint`, `pnpm test`

## Code Style

### Python (Backend)

- Python 3.12+, strict typing, `from __future__ import annotations`
- Ruff for linting, mypy for type checking
- FastAPI + Pydantic for API and config
- `async`/`await` throughout

### TypeScript (Frontend)

- Svelte 5 with runes (`$state`, `$derived`, `$effect`, `$props`)
- Tailwind CSS v4 for styling
- Svelte stores for WebSocket state

## Project Structure

```
backend/src/
  main.py           # FastAPI entry point
  config.py         # Pydantic settings
  robot/            # Reachy Mini SDK wrapper
  agent/            # LLM orchestrator + providers + tools
  voice/            # Voice engine (PersonaPlex + cloud fallback)
  vision/           # Camera stream + multimodal analysis
  integrations/     # Plugin system (Outlook, Calendar, Obsidian)
  api/              # REST + WebSocket endpoints

frontend/src/
  routes/           # SvelteKit pages (dashboard, integrations, settings)
  lib/components/   # UI components
  lib/stores/       # Svelte stores (robot, chat, video, settings)
  lib/types/        # TypeScript interfaces
```

## Boundaries

### Always Do

- Use `pnpm` for frontend, `uv` for backend
- Follow conventional commit format
- Add tests for new functionality
- Use type annotations in both Python and TypeScript

### Never Do

- Commit secrets, API keys, or .env files
- Push directly to `main` branch
- Use `any` type without justification
- Skip tests for new features
