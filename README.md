# HUGO — Helpful Universal Guide & Organizer

A voice-first, embodied personal assistant. HUGO lives on local compute (a
DGX Spark) and a Reachy Mini robot body: say the wake word, talk to it like
a person, and everything — speech recognition, reasoning, tool use, speech
synthesis — runs on hardware you own. No cloud LLM in the loop.

Say **"hey jarvis"** → chime → ask → first spoken words in ~2 seconds.
Follow up without re-waking. Say **"stop"** to end the conversation, or
**"go to sleep"** to shut the whole stack down and hand the machine back.

## Stack

| Piece | What | Where |
|---|---|---|
| Brain | Nemotron-3-Super-120B (NVFP4) on vLLM, reasoning off, MTP decoding | `.venv-vllm` |
| Ears | NVIDIA Parakeet TDT 1.1B (NeMo), one transcription per utterance | `.venv-stt` |
| Voice | Qwen3-TTS CustomVoice via faster-qwen3-tts (CUDA-graph streaming) | `.venv-tts` |
| Wake/VAD | openWakeWord + Silero VAD | in-process |
| Body | Reachy Mini (mic, speaker, rest posture) | in-process |

The voice loop streams end to end: LLM tokens are sentence-split and spoken
while generation continues, tool calls are verbally acknowledged, and long
work gets "still on it" nudges. See `CONTEXT.md` for the domain language,
`docs/adr/` for the decisions, and `CLAUDE.md` for operational notes.

## Running it (on the robot's machine)

```
scripts/setup_service_venv.sh vllm   # once per service: vllm, stt, tts
uv sync --group robot                # main venv + robot SDK
scripts/install_systemd_service.sh   # installs the systemd user service

systemctl --user start hugo          # ~4-5 min model load, then listening
journalctl --user -u hugo -f         # logs
systemctl --user stop hugo           # graceful sleep
```

CLI equivalents: `hugo start` (foreground), `hugo sleep`, `hugo stop`,
`hugo status`, `hugo forget`, and `hugo dev ...` hardware checks.
Configuration is env vars prefixed `HUGO_` (see `src/hugo/config.py`);
secrets live in `~/.hugo_secrets`.

## Development

```
uv sync
pytest tests/unit && mypy && ruff check . && ruff format --check .
```

Unit tests fake all hardware at Protocol seams — the voice loop's state
machine, interruption, and conversation lifecycle are fully proven without
a robot. `pytest -m integration` (on the DGX, services up) runs live
regression tests, including a no-human full cascade: HUGO's TTS speaks a
question, its STT transcribes it back, its LLM answers.
