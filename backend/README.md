# HUGO Backend

FastAPI backend for HUGO — voice, vision, and AI reasoning.

## Prerequisites

- Apple Silicon Mac (M1+) — required for MLX models
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
cd backend
uv sync --extra dev  # Install all dependencies including dev tools
```

## Running

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8080
```

## Voice Pipeline

The voice pipeline runs a mic → VAD → STT → OpenClaw → TTS → speaker loop.

### Models (auto-download on first run)

| Model                                  | Size    | Purpose                      |
| -------------------------------------- | ------- | ---------------------------- |
| `mlx-community/whisper-large-v3-turbo` | ~4 GB   | Speech-to-text (MLX Whisper) |
| `mlx-community/Kokoro-82M-bf16`        | ~300 MB | Text-to-speech (Kokoro)      |
| `snakers4/silero-vad` (via torch.hub)  | ~5 MB   | Voice activity detection     |

Models download from Hugging Face Hub / PyTorch Hub on first run. Ensure you have sufficient disk space and internet connectivity.

### Environment Variables

| Variable              | Default                                | Description                      |
| --------------------- | -------------------------------------- | -------------------------------- |
| `HUGO_OPENCLAW_URL`   | `ws://127.0.0.1:18789`                 | OpenClaw gateway WebSocket URL   |
| `HUGO_OPENCLAW_TOKEN` | (empty)                                | OpenClaw authentication token    |
| `HUGO_GEMINI_API_KEY` | (empty)                                | Google Gemini API key for vision |
| `HUGO_STT_MODEL`      | `mlx-community/whisper-large-v3-turbo` | STT model name                   |
| `HUGO_TTS_MODEL`      | `mlx-community/Kokoro-82M-bf16`        | TTS model name                   |
| `HUGO_TTS_VOICE`      | `af_heart`                             | TTS voice preset                 |
| `HUGO_SAMPLE_RATE`    | `16000`                                | Audio sample rate (Hz)           |
| `HUGO_VAD_THRESHOLD`  | `0.5`                                  | VAD confidence threshold         |

## Testing

```bash
uv run python -m pytest -v
```

## Linting

```bash
uv run ruff check src/ tests/
```
