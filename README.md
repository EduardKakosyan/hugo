# HUGO

Voice-first personal assistant embodied in a Reachy Mini robot. Uses CrewAI multi-agent orchestration, MCP servers for external services, and runs primarily on local MLX models.

## Quick Start

```bash
# Install Python dependencies
uv sync --dev

# Install git hook dependencies
pnpm install

# Run in simulation mode (no robot needed)
uv run python -m src.main --sim --no-voice

# Run with voice pipeline
uv run python -m src.main --sim

# Run full mode (robot + voice)
uv run python -m src.main
```

## Architecture

- **Voice Pipeline**: Silero VAD + Whisper V3 Turbo (STT) + Kokoro-82M (TTS) — all local via MLX
- **Semantic Router**: nomic-embed-text V2 for sub-ms intent classification
- **Agent Framework**: CrewAI with 7 specialist agents
- **MCP Servers**: Microsoft Graph, Linear, Fireflies.ai
- **Robot**: Reachy Mini SDK with simulation mode for development

## Development

```bash
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run mypy src/             # Type check
uv run pytest --cov=src      # Test with coverage
```

See [CLAUDE.md](CLAUDE.md) for detailed development instructions.
