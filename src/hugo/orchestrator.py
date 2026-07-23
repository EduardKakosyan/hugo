"""Composes every built piece into a real `hugo start`/`hugo stop`.

`hugo start` spawns vLLM/STT/TTS as subprocesses (each in its own venv —
see docs/adr/0005 and scripts/setup_service_venv.sh), waits for them to
become healthy, wires up the in-process components (robot client, wake
word, VAD, STT/TTS clients, LLM client + tool loop, memory store) into a
VoiceLoop, and runs until SIGINT/SIGTERM. `hugo stop` (a separate process
invocation) reads the pidfile and uses the group-kill safety net — see
docs/adr/0002.

Runs for real on dgx1 (first clean end-to-end voice turn 2026-07-22;
conversational-latency stack verified live 2026-07-23 — see VEN-56 and
tests/integration/). Startup is staged for the shared 121GB unified
memory pool: STT+TTS concurrently, then vLLM with streamed weight
loading and continuous page-cache eviction, with the robot daemon
connecting alongside — ~4m45s to listening, measured.
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
from hugo.supervisor.page_cache import evict_directory_from_page_cache, hf_model_cache_dir
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


def _build_specs(config: Config) -> list[list[ManagedProcessSpec]]:
    """Startup stages (VEN-56 load-time work): STT and TTS first,
    concurrently — they're a few GB each and their CUDA loads must happen
    BEFORE vLLM's 74.8GB checkpoint read can fill the page cache (the
    reproduced STT-OOM ordering) — then vLLM alone."""
    llm_port = urlsplit(config.llm_base_url).port

    async def evict_llm_checkpoint_from_page_cache() -> None:
        # Unified memory: vLLM's 74.8GB checkpoint read fills the page
        # cache and CUDA allocation doesn't force reclaim — a real CUDA
        # OOM, reproduced 2026-07-22 and 2026-07-23. Staging STT/TTS
        # before vLLM removes the original victim, but runtime allocations
        # (TTS synthesis buffers, vLLM's own warmup) still benefit from
        # the headroom: the weights are on the GPU once vLLM is healthy,
        # so the cached file pages are pure dead weight.
        checkpoint_dir = hf_model_cache_dir(config.llm_model)
        evicted = await asyncio.to_thread(evict_directory_from_page_cache, checkpoint_dir)
        logger.info("evicted %.1f GiB of %s from the page cache", evicted / 2**30, checkpoint_dir)

    stt_and_tts = [
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
            # server runs (see tts_server._warmup_then_serve).
            health_check_timeout=240.0,
        ),
    ]
    vllm = [
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
                # History: 0.75 OOMed STT on 2 of 3 restarts when STT
                # loaded AFTER vLLM (page cache from the 74.8GB checkpoint
                # read — since root-caused and fixed by eviction), so 0.65
                # was chosen defensively. The staged startup inverts the
                # order (STT/TTS resident BEFORE vLLM profiles), which
                # retires that failure mode — and 0.65 proved too tight
                # live on 2026-07-23: weights + MTP drafter ≈ 75GB against
                # a 78.6GB budget left the KV pool at the mercy of
                # page-cache noise (engine init failed twice). 0.72 ≈
                # 87GB budget → ~12GB KV pool, with stt+tts+system ≈ 10GB
                # outside it and ~24GB true slack on the 121GB pool.
                "--gpu-memory-utilization",
                "0.72",
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
                # ToolLoop sends `tools=` on every turn. Without these,
                # vLLM rejects any request containing `tools` with a real
                # 400 Bad Request — confirmed directly on dgx1: the very
                # first conversation silently killed the voice loop's
                # background task. qwen3_coder is NVIDIA's documented
                # tool-call-parser for this model family, including the
                # NVFP4 quant; no Nemotron-specific tool parser exists.
                "--enable-auto-tool-choice",
                "--tool-call-parser",
                "qwen3_coder",
                # THE VEN-56 root-cause fix. Nemotron 3 has reasoning ON by
                # default, and its chat template puts the opening <think>
                # tag in the *prompt* — so without a reasoning parser the
                # entire trace lands in message.content and gets SPOKEN
                # (the "recites its own system prompt" symptom), and
                # generating it (~800-1000 tokens at ~16 tok/s measured in
                # /tmp/hugo_start.log) was the 40s of dead air. nemotron_v3
                # is built into vLLM >= 0.20 (0.25.0 installed on dgx1);
                # it separates the trace into the `reasoning` field, which
                # the client never speaks (CONTEXT.md: Reasoning trace).
                "--reasoning-parser",
                "nemotron_v3",
                # Thinking off by default server-side: a voice assistant
                # answers now, not after a thinking budget. Per-request
                # chat_template_kwargs can still re-enable it later.
                "--default-chat-template-kwargs",
                '{"enable_thinking": false}',
                # MTP speculative decoding from NVIDIA's own DGX Spark
                # recipe for this exact model: ~16 -> ~23 tok/s decode.
                # Needs vLLM >= 0.19 (streaming tool-call fix under MTP,
                # vllm#35615) — 0.25.0 satisfies it.
                "--speculative-config",
                '{"method": "mtp", "num_speculative_tokens": 3, "moe_backend": "triton"}',
                # Parallel weight streaming (VEN-56 load-time work): the
                # default safetensors loader read the checkpoint at
                # ~120MB/s while the NVMe delivers 4.6GB/s single-stream
                # (both measured on dgx1, 2026-07-23) — ~10 of the ~11
                # startup minutes were this one bottleneck. Requires the
                # vllm[runai] extra (see deploy/vllm/requirements.txt).
                "--load-format",
                "runai_streamer",
                # The staging buffer MUST be bounded on unified memory:
                # left unlimited, the MTP drafter's second streaming pass
                # (with ~70GB of target weights already resident) killed
                # the EngineCore silently at 17% with throughput collapsing
                # 3373->390 it/s — classic memory-exhaustion death, seen
                # live on dgx1 2026-07-23. 4GiB staging + bounded
                # concurrency keeps the second pass inside the pool.
                "--model-loader-extra-config",
                '{"concurrency": 8, "memory_limit": 4294967296}',
                # The model default is 262144 — 1.88GiB of KV cache per
                # max-length request, which made KV sizing fail outright
                # on the shared pool (live on dgx1 2026-07-23). A voice
                # conversation is a few thousand tokens; 32k is ~8x
                # headroom over any real session at 1/8th the KV demand.
                "--max-model-len",
                "32768",
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
            # VLLM_NVFP4_GEMM_BACKEND=marlin is from NVIDIA's DGX Spark
            # recipe for this model (pairs with the MTP speculative
            # config above for the published ~23 tok/s decode).
            extra_env={"MAX_JOBS": "4", "VLLM_NVFP4_GEMM_BACKEND": "marlin"},
            after_healthy=evict_llm_checkpoint_from_page_cache,
        ),
    ]
    return [stt_and_tts, vllm]


async def run(config: Config) -> None:
    if not config.tavily_api_key:
        raise RuntimeError(
            "HUGO_TAVILY_API_KEY is not set — required for the web search "
            "tool, v1's only LLM tool. Get a key at https://tavily.com."
        )

    process_manager = ProcessManager(pidfile=Pidfile(config.pidfile_path))
    logger.info("starting model servers (stt+tts, then vllm) and connecting robot...")
    # Robot connect overlaps the server startup (VEN-56 load-time work):
    # a cold reachy-mini daemon takes ~40s of spawn+retry that used to run
    # serially after the models. ReachyMiniClient's constructor is
    # blocking, hence to_thread.
    robot_task = asyncio.create_task(
        asyncio.to_thread(ReachyMiniClient, playback_gain=config.playback_gain)
    )

    async def keep_checkpoint_out_of_page_cache() -> None:
        # vLLM sizes its KV cache from *free* memory at profile time, and
        # on unified memory the checkpoint file pages the streamer has
        # already consumed count against it — measured live on dgx1
        # (2026-07-23): 17GB of buff/cache at profiling collapsed the KV
        # pool to 0.15GiB and engine init failed. Evict continuously while
        # the servers come up; re-reading a not-yet-consumed page costs
        # ~nothing at the NVMe's measured 4.6GB/s. The vllm spec's
        # after_healthy hook does the final sweep.
        checkpoint_dir = hf_model_cache_dir(config.llm_model)
        while True:
            await asyncio.to_thread(evict_directory_from_page_cache, checkpoint_dir)
            # The streamer reads at ~4GB/s — a 15s sweep interval let tens
            # of GB of cache accumulate between sweeps and vLLM profiled
            # inside a dirty window (live failure #2). Sweep aggressively;
            # each sweep is a cheap fadvise walk over 17 files.
            await asyncio.sleep(5.0)

    eviction_task = asyncio.create_task(keep_checkpoint_out_of_page_cache())
    try:
        await process_manager.start_stages(_build_specs(config))
    except BaseException:
        # to_thread can't interrupt a mid-flight connect; wait it out and
        # release the media pipeline if it succeeded, then let the startup
        # failure propagate.
        robot_task.cancel()
        with contextlib.suppress(BaseException):
            (await robot_task).close()
        raise
    finally:
        eviction_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await eviction_task
    logger.info("model servers healthy")

    # Everything past server startup runs under this try/finally: a
    # failure anywhere here (found live 2026-07-23 — ReachyMiniClient
    # raising FileNotFoundError for the daemon binary) must still tear the
    # model servers down, or ~90GB of a teammate's memory leaks until
    # someone notices (ADR 0002's guarantee, and exactly what happened: an
    # orphaned EngineCore held 80GB+ after the crash).
    try:
        memory_store = MemoryStore(config.memory_db_path)
        await memory_store.initialize()

        robot = await robot_task
        # Physically stand up before speaking: the motors stay in rest
        # posture from the last sleep otherwise, and a slumped robot reads
        # as 'asleep' regardless of what the voice does. Best-effort — a
        # motor fault must not block the voice stack.
        try:
            await robot.wake_up()
        except Exception:
            logger.exception("failed to stand the robot up; continuing")
        stt = SttClient(config.stt_ws_url)
        await stt.connect()
        tts = TtsClient(config.tts_ws_url)
        await tts.connect()
        llm = LlmClient(base_url=config.llm_base_url, model=config.llm_model)
        web_search = WebSearchTool(config.tavily_api_key)

        # First-inference warmup: the first live turn paid 12.77s to first
        # audio vs ~3.5s warm (dgx1, 2026-07-23) — cold CUDA paths and an
        # empty prefix cache. One throwaway request eats that cost before
        # the wake word can. Best-effort: a failure here is a warning, not
        # a startup failure.
        try:
            async with asyncio.timeout(60.0):
                await llm.complete([{"role": "user", "content": "Say the word ready."}])
            logger.info("llm warmup complete")
        except Exception:
            logger.warning("llm warmup failed; first turn will be slow", exc_info=True)

        stop_event = asyncio.Event()

        voice_loop = VoiceLoop(
            robot=robot,
            wake_word=WakeWordDetector(model_name=config.wake_word),
            vad=SpeechActivityDetector(),
            stt=stt,
            tts=tts,
            thinker=ToolLoop(llm, web_search=web_search),
            tts_sample_rate_hz=config.tts_sample_rate_hz,
            no_speech_timeout_s=config.no_speech_timeout_s,
            follow_up_window_s=config.follow_up_window_s,
            max_utterance_s=config.max_utterance_s,
            progress_update_after_s=config.progress_update_after_s,
            stop_phrases=config.stop_phrases,
            sleep_phrases=config.sleep_phrases,
            interrupt_wake_score=config.interrupt_wake_score,
            # Spoken "go to sleep" and `hugo sleep`'s SIGTERM converge on
            # the same graceful shutdown below (CONTEXT.md: Sleep).
            on_sleep=stop_event.set,
            # The audible "load is done, wake word works now" — the wake
            # chime from the sleeping ear fired minutes earlier (see
            # wake_listener.py).
            startup_announcement="I'm awake.",
        )

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
        # Rest posture before releasing the robot: the physical cue that
        # HUGO is off (VEN-56). Best-effort — a motor fault must not block
        # the memory-release guarantee (ADR 0002).
        try:
            await robot.goto_sleep()
        except Exception:
            logger.exception("failed to move robot to rest posture")
        robot.close()
    finally:
        await process_manager.stop_all()
        logger.info("hugo stopped, all model memory released")
