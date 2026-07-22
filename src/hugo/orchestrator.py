"""Composes every built piece into a real `hugo start`/`hugo stop`.

`hugo start` spawns vLLM/STT/TTS as subprocesses (each in its own venv —
see docs/adr/0005 and scripts/setup_service_venv.sh), waits for them to
become healthy, wires up the in-process components (robot client, wake
word, VAD, STT/TTS clients, LLM client + tool loop, memory store) into a
VoiceLoop, and runs until SIGINT/SIGTERM. `hugo stop` (a separate process
invocation) reads the pidfile and uses the group-kill safety net — see
docs/adr/0002.

NOT YET run for real end-to-end: doing so means loading the actual
~60-70GB Nemotron-3 model on the *shared* dgx1 box, which needs explicit
coordination (not a quick spike) — see the M1.11 notes in the plan.
M1.9 already verified LlmClient/ToolLoop against a real (small) vLLM
server; M1.5's ReachyMiniClient is grounded in the real SDK API but has no
physically-connected robot to test against yet.
"""

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets

from hugo.agent.llm_client import LlmClient
from hugo.agent.tool_loop import ToolLoop
from hugo.agent.web_search import WebSearchTool
from hugo.config import Config
from hugo.memory.store import MemoryStore
from hugo.robot.reachy_client import ReachyMiniClient
from hugo.supervisor.pidfile import Pidfile
from hugo.supervisor.process_manager import ManagedProcessSpec, ProcessManager
from hugo.voice.loop import VoiceLoop
from hugo.voice.stt import SttClient
from hugo.voice.tts import TtsClient
from hugo.voice.vad import SpeechActivityDetector
from hugo.voice.wake_word import WakeWordDetector

logger = logging.getLogger(__name__)

HealthCheck = Callable[[], Awaitable[bool]]


def _http_health_check(base_url: str, health_path: str = "/health") -> HealthCheck:
    parts = urlsplit(base_url)
    health_url = urlunsplit((parts.scheme, parts.netloc, health_path, "", ""))

    async def check() -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    return check


def _websocket_health_check(url: str) -> HealthCheck:
    async def check() -> bool:
        try:
            async with websockets.connect(url, open_timeout=2.0):
                return True
        except OSError:
            return False

    return check


def _build_specs(config: Config) -> list[ManagedProcessSpec]:
    llm_port = urlsplit(config.llm_base_url).port
    return [
        ManagedProcessSpec(
            name="vllm",
            # --port is explicit, not left to vLLM's own default — that
            # default happens to also be 8000, which collides with the
            # Reachy Mini daemon's own default port and caused a real
            # "Address already in use" crash on dgx1 when this wasn't set.
            command=[
                str(config.vllm_executable),
                "serve",
                config.llm_model,
                "--port",
                str(llm_port),
                # vLLM's default gpu_memory_utilization (~0.9) claims nearly
                # the *entire* 121GB unified memory pool for itself (weights
                # + KV cache) — fine for a single-model dedicated deployment,
                # but confirmed directly on dgx1 to starve STT/TTS out of GPU
                # memory afterward (a real CUDA OOM loading Parakeet TDT
                # right after vLLM became healthy). 0.75 (~30GB nominal
                # headroom) was *also* confirmed directly on dgx1 to still
                # OOM STT on 2 of 3 real restarts — vLLM's own log showed it
                # landing right on target (69.62GiB weights + 19.56GiB KV
                # cache + ~1GiB CUDA graph pool = ~90.2GiB, against a 90.75GiB
                # target), so the nominal ~30GB headroom just isn't reliably
                # free in practice (page-cache pressure from reading the
                # 74.8GB checkpoint off disk is the leading suspect, not yet
                # fully root-caused). 0.65 (~42GB nominal headroom) trades
                # some KV cache size for a real safety margin.
                "--gpu-memory-utilization",
                "0.65",
                # NemotronH is a hybrid Mamba/attention architecture: each
                # concurrent sequence needs its own Mamba cache block, and
                # vLLM's workload-derived default max_num_seqs (256, sized
                # for multi-tenant serving) needs more blocks than 0.65
                # utilization leaves room for — confirmed directly on dgx1,
                # vLLM refused to start with a real, explicit ValueError
                # ("max_num_seqs (256) exceeds available Mamba cache blocks
                # (181)"). HUGO is single-user with one conversation in
                # flight at a time (see CONTEXT.md/ADRs) — 256-way
                # concurrency was never needed; 8 leaves slack for internal
                # concurrency (e.g. a health check alongside a real turn)
                # without hitting the Mamba cache ceiling.
                "--max-num-seqs",
                "8",
                # ToolLoop (Milestone 2) sends `tools=` on every turn.
                # Without these, vLLM rejects any request containing
                # `tools` with a real 400 Bad Request — confirmed directly
                # on dgx1: the very first conversation silently killed the
                # voice loop's background task (see voice/loop.py's
                # _run_thinking fix). qwen3_coder is NVIDIA's documented
                # tool-call-parser for this model family, including the
                # NVFP4 quant (vLLM's Nemotron 3 Super blog post, and the
                # model's own HF discussions).
                "--enable-auto-tool-choice",
                "--tool-call-parser",
                "qwen3_coder",
            ],
            health_check=_http_health_check(config.llm_base_url),
            # A ~80GB MoE model load is realistically minutes, not seconds —
            # and CUDA graph capture / torch.compile for this model size can
            # take longer than 30 minutes on its own, confirmed directly on
            # dgx1 (a 1800s timeout was hit mid-compilation with no errors,
            # just still working). 60 minutes total budget instead.
            health_check_timeout=3600.0,
            health_check_interval=5.0,
            # flashinfer JIT-compiles ~29 CUDA kernel variants via ninja,
            # which defaults to nproc (20 on dgx1) parallel nvcc jobs —
            # confirmed directly on dgx1 that this gets individual nvcc
            # invocations OOM-killed while the ~80GB model is concurrently
            # loading into the same unified memory pool. Capped here.
            extra_env={"MAX_JOBS": "4"},
        ),
        ManagedProcessSpec(
            name="stt",
            command=[str(config.stt_server_python), "-m", "hugo.servers.stt_server"],
            health_check=_websocket_health_check(config.stt_ws_url),
            health_check_timeout=120.0,
        ),
        ManagedProcessSpec(
            name="tts",
            command=[str(config.tts_server_python), "-m", "hugo.servers.tts_server"],
            health_check=_websocket_health_check(config.tts_ws_url),
            # Covers model load AND the pre-bind warmup synthesis the
            # server now runs (see tts_server._warmup_then_serve).
            health_check_timeout=240.0,
        ),
    ]


async def run(config: Config) -> None:
    if not config.tavily_api_key:
        raise RuntimeError(
            "HUGO_TAVILY_API_KEY is not set — required for the web search "
            "tool, v1's only LLM tool. Get a key at https://tavily.com."
        )

    process_manager = ProcessManager(pidfile=Pidfile(config.pidfile_path))
    logger.info("starting model servers (vllm, stt, tts)...")
    await process_manager.start_all(_build_specs(config))
    logger.info("model servers healthy")

    memory_store = MemoryStore(config.memory_db_path)
    await memory_store.initialize()

    robot = ReachyMiniClient()
    stt = SttClient(config.stt_ws_url)
    await stt.connect()
    tts = TtsClient(config.tts_ws_url)
    await tts.connect()
    llm = LlmClient(base_url=config.llm_base_url, model=config.llm_model)
    web_search = WebSearchTool(config.tavily_api_key)

    voice_loop = VoiceLoop(
        robot=robot,
        wake_word=WakeWordDetector(model_name=config.wake_word),
        vad=SpeechActivityDetector(),
        stt=stt,
        tts=tts,
        thinker=ToolLoop(llm, web_search=web_search),
        tts_sample_rate_hz=config.tts_sample_rate_hz,
    )

    stop_event = asyncio.Event()
    running_loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        running_loop.add_signal_handler(sig, stop_event.set)

    voice_task = asyncio.create_task(voice_loop.run())
    logger.info("hugo is running — say '%s' to start a conversation", config.wake_word)
    await stop_event.wait()

    logger.info("shutting down...")
    voice_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await voice_task
    await stt.close()
    await tts.close()
    robot.close()
    await process_manager.stop_all()
    logger.info("hugo stopped, all model memory released")
