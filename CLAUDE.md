# HUGO — working notes for agents

Voice-first embodied assistant: wake word → STT → LLM (tool loop) → TTS on a
Reachy Mini robot, all inference local on a shared DGX Spark ("dgx1", 121GB
unified memory, aarch64/CUDA). Domain glossary: `CONTEXT.md`. Decisions:
`docs/adr/`. Tracker: Linear project "HUGO" (Ventures team).

## Deployment reality

- Dev happens on a Mac; dgx1 runs the deployed checkout at `~/hugo` under the
  **shared team account `jim`**. Deploy = commit → push → `git pull` on dgx1.
- Per-service venvs (ADR 0005): `.venv` (orchestrator+robot), `.venv-vllm`,
  `.venv-stt`, `.venv-tts` — created by `scripts/setup_service_venv.sh`.
  Manage with `uv pip install --python .venv-X/bin/python ...` (no pip binary).
- Secrets: `~/.hugo_secrets` on dgx1, plain `KEY=VALUE` lines (systemd
  EnvironmentFile format — no `export`). Holds `HUGO_TAVILY_API_KEY`,
  `HUGO_PLAYBACK_GAIN`.

## Running HUGO on dgx1

Preferred: the systemd user service (`scripts/install_systemd_service.sh`):

    systemctl --user start hugo     # ~3-4 min: models load, then voice loop
    systemctl --user stop hugo      # graceful sleep (rest posture + teardown)
    journalctl --user -u hugo -f    # persistent logs

Manual fallback (never `setsid` — see gotchas):

    tmux new-session -d -s hugo 'bash -c "cd ~/hugo && set -a && source ~/.hugo_secrets && set +a && .venv/bin/hugo start 2>&1 | tee /tmp/hugo_start.log"'

`hugo sleep` = graceful remote stop; `hugo stop` = group-kill safety net;
`hugo forget` wipes the persistent facts DB (refuses while running).

## Hard rules learned on hardware (violate = hours of debugging)

- **Shared box etiquette (ADR 0002):** HUGO must never leave model memory
  claimed when not running. After any crash experiment, verify with
  `free -g` — a vLLM `EngineCore` child can outlive its parent holding 80GB.
- **One gstreamer pipeline** for mic+speaker on the robot: never call
  `stop_playing()`/`stop_recording()` mid-session (kills capture or
  deadlocks). Barge-in flushes via `clear_playback()`. See `voice/loop.py`.
- **Page cache is the enemy on unified memory:** the 74.8GB checkpoint read
  fills it and CUDA allocs don't force reclaim — startup order, the eviction
  hooks (`supervisor/page_cache.py`), and vLLM's KV sizing all depend on it.
- **Reasoning trace must never reach TTS** (CONTEXT.md): vLLM runs
  `--reasoning-parser nemotron_v3` + thinking off. The regression test is
  `tests/integration/test_voice_stack.py::test_reasoning_trace_never_reaches_spoken_content`.
- **TTS WebSocket is one-connection-per-utterance** (stale-terminator bug,
  regression-tested). Don't "optimize" it back to a shared connection.
- **No AEC yet:** interruption while HUGO speaks is wake-word-gated
  (ADR 0003 as amended). Don't re-enable VAD barge-in without AEC.

## Ops gotchas (from live sessions)

- `hugo start` must NOT be a session leader ancestor-wrapped via `setsid`
  (EPERM crash pre-b38a3ee; now tolerated, but don't anyway). systemd is fine.
- `pkill -f <pattern>` over SSH: bracket-escape (`pkill -f "[s]tt_server"`)
  or it matches the SSH command itself and kills your own session.
- `/tmp/hugo_start.log` truncates on each manual relaunch — capture evidence
  before restarting. journald (systemd path) doesn't have this problem.
- vLLM startup is staged and self-evicting; if engine init fails on KV cache
  sizing, suspect page-cache accumulation or the `--gpu-memory-utilization`
  ↔ resident-services balance (comments in `orchestrator._build_specs`).
- `dmesg` is restricted for `jim` — kernel OOM kills are invisible; infer
  from silent process death + `free -g`.

## Testing

- `pytest tests/unit` + `mypy` (strict) + `ruff check` + `ruff format --check`
  must all pass — CI enforces all four.
- `pytest -m integration` on dgx1 with services up: live regression tests
  incl. conversational quality and a full TTS→STT→LLM cascade, no human
  needed. Tests skip per-service when a server is unreachable.
- Unit tests fake all hardware at Protocol seams (`tests/unit/voice/fakes.py`);
  keep the fake robot's sample rates mismatched from TTS so the resampler
  stays honest.
