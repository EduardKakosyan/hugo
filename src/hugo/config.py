"""HUGO configuration, loaded from environment variables (prefix HUGO_)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_state_dir() -> Path:
    return Path.home() / ".local" / "state" / "hugo"


class Config(BaseSettings):
    """Runtime configuration for the HUGO orchestrator and its subprocesses."""

    model_config = SettingsConfigDict(env_prefix="HUGO_")

    state_dir: Path = _default_state_dir()
    log_level: str = "INFO"

    # Placeholder until a custom "Hey HUGO" model is trained (see
    # voice/wake_word.py) — "hey_jarvis" is the stock pretrained phrase
    # actually in use right now.
    wake_word: str = "hey_jarvis"

    # Port 8000 is deliberately avoided — it's the Reachy Mini daemon's own
    # default port (see robot/reachy_client.py), confirmed colliding via a
    # real "OSError: [Errno 98] Address already in use" on dgx1.
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    # NVFP4 (NVIDIA's native 4-bit format, ~80GB total download) matches
    # ADR 0004's "4-bit quant, ~60-70GB" and GB10/Blackwell's native FP4
    # tensor core support. Verified as a real, public (non-gated) HF repo
    # on 2026-07-13 — the previous placeholder "nemotron-3-super-120b-a12b"
    # was never a real model ID and caused a real 401/RepositoryNotFoundError
    # crash on dgx1.
    llm_model: str = "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4"
    stt_ws_url: str = "ws://127.0.0.1:8001"
    tts_ws_url: str = "ws://127.0.0.1:8002"
    # Native output rate of the TTS model (Qwen3-TTS synthesizes at 24kHz —
    # see servers/qwen_tts_synthesizer.py). The voice loop resamples from
    # this to the robot's actual speaker rate (16kHz on the Reachy Mini).
    tts_sample_rate_hz: int = 24_000

    # v1's only LLM tool (web search, via Tavily). Loads as HUGO_TAVILY_API_KEY
    # like everything else here, even though Tavily's own docs usually expect
    # a bare TAVILY_API_KEY -- passed explicitly into WebSearchTool rather
    # than auto-read by any SDK. Optional here (not required) so Config stays
    # constructible for hugo dev subcommands and tests that don't touch
    # search; orchestrator.run() fails fast on a missing key instead, since
    # that's the only path that actually needs it.
    tavily_api_key: str | None = None

    # Where the per-service venvs created by scripts/setup_service_venv.sh
    # live (see docs/adr/0005) — `hugo start` assumes it's run from the
    # repo root, matching the dev workflow (`git pull && hugo start`).
    repo_dir: Path = Path.cwd()

    @property
    def pidfile_path(self) -> Path:
        return self.state_dir / "hugo.pid"

    @property
    def memory_db_path(self) -> Path:
        return self.state_dir / "memory.db"

    @property
    def vllm_executable(self) -> Path:
        return self.repo_dir / ".venv-vllm" / "bin" / "vllm"

    @property
    def stt_server_python(self) -> Path:
        return self.repo_dir / ".venv-stt" / "bin" / "python"

    @property
    def tts_server_python(self) -> Path:
        return self.repo_dir / ".venv-tts" / "bin" / "python"


def load_config() -> Config:
    config = Config()
    config.state_dir.mkdir(parents=True, exist_ok=True)
    return config
