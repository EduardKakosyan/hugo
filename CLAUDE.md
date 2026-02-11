# CLAUDE.md

This file provides guidance to Claude Code when working with the HUGO codebase.

## Project Overview

HUGO is a **voice-first personal assistant** embodied in a **Reachy Mini robot**. It uses CrewAI for multi-agent orchestration, MCP servers for external service integration, and runs primarily on local MLX models on Apple Silicon.

## Tech Stack

- **Language**: Python 3.12 (strict typing)
- **Agent Framework**: CrewAI (agents.yaml + tasks.yaml config)
- **Voice Pipeline**: Pipecat + Silero VAD + Whisper V3 Turbo + Kokoro TTS (all MLX)
- **LLM (local)**: Qwen3-32B via MLX-LM
- **Vision (local)**: Qwen3-VL 4B via MLX-VLM
- **Routing**: semantic-router with nomic-embed-text V2
- **MCP Servers**: FastMCP (ms_graph, linear, fireflies)
- **Robot SDK**: reachy-mini
- **Package Manager**: uv (NOT pip, NOT poetry)
- **Linting**: ruff
- **Type Checking**: mypy (strict)
- **Testing**: pytest + pytest-asyncio
- **CI/CD**: GitHub Actions + Husky hooks

## Commands

```bash
# Package Management (ALWAYS use uv)
uv sync                      # Install dependencies
uv sync --dev                # Install with dev deps
uv run <command>             # Run within venv

# Code Quality
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run ruff check --fix .    # Auto-fix lint issues
uv run mypy src/             # Type check

# Testing
uv run pytest                # Run all tests
uv run pytest --cov=src      # Run with coverage
uv run pytest -k "test_name" # Run specific test

# Running HUGO
uv run python -m src.main --sim              # Simulation mode (no robot)
uv run python -m src.main --sim --no-voice   # Text-only mode
uv run python -m src.main                    # Full mode (needs robot)

# Security
pnpm secrets:check           # Scan staged files for secrets
pnpm secrets:scan            # Full repo secret scan

# Git hooks (Node.js for commitlint/husky)
pnpm install                 # Install hook dependencies
pnpm prepare                 # Set up husky
```

## Git Workflow

**Branching Strategy:**

- `main` is protected — no direct pushes
- Create feature branches from `dev`
- Only `dev` merges into `main` via PR
- Branch naming: `feat/description`, `fix/description`, `chore/description`

**Commit Message Format (enforced by commitlint):**

- Format: `type: description` (lowercase, max 100 chars)
- Types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `ci`, `perf`

**Before Committing:**

1. `uv run ruff check . && uv run ruff format --check .`
2. `uv run mypy src/`
3. `uv run pytest`

## Project Structure

```
src/
  main.py              # Entry point (--sim, --no-voice flags)
  config/
    agents.yaml        # CrewAI agent definitions (7 agents)
    tasks.yaml         # CrewAI task definitions (7 tasks)
  flows/
    assistant_flow.py  # Main interaction loop (Flow with @start/@listen)
  crews/
    assistant_crew.py  # CrewBase wiring agents + MCP tools
  router/
    intent_router.py   # Semantic router (nomic-embed-text V2)
  voice/
    pipeline.py        # Pipecat: VAD → STT → TTS (all local MLX)
  robot/
    controller.py      # Reachy Mini SDK wrapper (sim mode supported)
  mcp_servers/
    ms_graph.py        # Email, calendar, files (Microsoft Graph)
    linear_server.py   # Issues, projects (Linear GraphQL)
    fireflies.py       # Meeting transcripts (Fireflies GraphQL)
  tools/
    robot_tools.py     # CrewAI tools: speak, look_at, express, rotate
    vision_tools.py    # CrewAI tools: capture_frame, describe_scene
  models/
    schemas.py         # Pydantic models for all structured outputs
tests/
  conftest.py          # Fixtures: mock robot, mock MCP
  test_router.py       # Intent routing tests
  test_crew.py         # YAML config validation tests
  test_tools.py        # Robot/vision tool tests
  test_mcp_servers.py  # MCP server tests
knowledge/             # CrewAI knowledge store
```

## Key Architecture Decisions

1. **Local-first**: 90% of inference on MLX (Qwen3-32B, Whisper, Kokoro)
2. **MCP for external services**: Each service (Graph, Linear, Fireflies) is a FastMCP server
3. **Semantic routing**: nomic-embed V2 classifies intents in sub-ms before hitting LLM
4. **Approval gates**: send_email, create_issue, create_event require explicit approval
5. **Simulation mode**: `--sim` flag for development without robot hardware

## Boundaries

### Always Do

- Use Python type hints (strict mypy)
- Follow existing patterns in the codebase
- Add tests for new functionality
- Run ruff/mypy/pytest before committing
- Use `uv` for package management
- Keep MCP servers as independent, testable modules

### Ask First

- Adding new dependencies
- Changing LLM model configurations
- Modifying CI/CD workflows
- Adding new MCP servers or agents

### Never Do

- Commit secrets, API keys, or .env files
- Push directly to `main`
- Use `Any` type without explicit justification comment
- Disable ruff rules without justification
- Skip tests for new features
- Use pip/poetry/npm for Python packages (use uv)
