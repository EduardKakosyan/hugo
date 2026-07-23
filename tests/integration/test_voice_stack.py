"""Integration tests against the real model servers (VEN-56) — run on the
DGX Spark with `hugo start`'s servers already up (or started manually):

    pytest -m integration

Each test skips (not fails) when its server isn't reachable, so the suite
can run piecemeal while only some services are up. These cover exactly
what the unit fakes cannot: that vLLM's reasoning parser actually keeps
the reasoning trace out of spoken content (the VEN-56 root-cause
regression test), that thinking is off by default, that streamed tool
calls parse, and that TTS/STT latencies are in budget under the real
models.
"""

import asyncio
import json
import math
import time

import pytest
import websockets

from hugo.agent.llm_client import AssistantTurn, LlmClient
from hugo.config import Config

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


async def _require_ws(url: str) -> None:
    try:
        ws = await websockets.connect(url, open_timeout=3.0)
        await ws.close()
    except OSError:
        pytest.skip(f"no server at {url}")


async def _require_llm(config: Config) -> None:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(config.llm_base_url.removesuffix("/v1") + "/health")
            if response.status_code != 200:
                pytest.skip("vLLM not healthy")
    except httpx.HTTPError:
        pytest.skip("vLLM not reachable")


async def test_reasoning_trace_never_reaches_spoken_content(config: Config) -> None:
    """THE regression test for the VEN-56 root cause: without
    --reasoning-parser nemotron_v3, the trace lands in message.content and
    gets spoken (the 'recites its own system prompt' bug)."""
    await _require_llm(config)
    client = LlmClient(base_url=config.llm_base_url, model=config.llm_model)

    started = time.monotonic()
    first_delta_at: float | None = None
    turn: AssistantTurn | None = None
    async for item in client.stream_with_tools(
        [
            {"role": "system", "content": "You are a voice assistant. Answer briefly."},
            {"role": "user", "content": "What can you do?"},
        ],
        tools=[],
    ):
        if isinstance(item, AssistantTurn):
            turn = item
        elif first_delta_at is None:
            first_delta_at = time.monotonic() - started

    assert turn is not None
    assert turn.content.strip(), "no spoken content at all"
    assert "<think" not in turn.content and "</think>" not in turn.content
    # Thinking off by default: the first content token must arrive in
    # seconds, not after an ~800-token reasoning trace (~40s at 20 tok/s).
    assert first_delta_at is not None and first_delta_at < 10.0, (
        f"first content delta took {first_delta_at:.1f}s — is enable_thinking"
        " really off (--default-chat-template-kwargs)?"
    )


async def test_streamed_tool_call_parses(config: Config) -> None:
    await _require_llm(config)
    from hugo.agent.web_search import WEB_SEARCH_TOOL_SCHEMA

    client = LlmClient(base_url=config.llm_base_url, model=config.llm_model)
    turn: AssistantTurn | None = None
    async for item in client.stream_with_tools(
        [
            {
                "role": "system",
                "content": "Use the web_search tool for anything about current events.",
            },
            {"role": "user", "content": "Search the web for today's weather in Halifax."},
        ],
        tools=[WEB_SEARCH_TOOL_SCHEMA],
    ):
        if isinstance(item, AssistantTurn):
            turn = item

    assert turn is not None
    assert turn.tool_calls, "model produced no tool call for an explicit search request"
    call = turn.tool_calls[0]
    assert call.name == "web_search"
    assert "query" in json.loads(call.arguments)


async def test_tts_first_audio_latency(config: Config) -> None:
    """VEN-56 budget: streaming TTS should produce first audio well under a
    second on idle GPU (author-measured 464ms on this hardware); 3s is the
    generous under-load ceiling before it hurts conversation."""
    await _require_ws(config.tts_ws_url)
    ws = await websockets.connect(config.tts_ws_url)
    try:
        started = time.monotonic()
        await ws.send(json.dumps({"type": "speak", "text": "Hello there, how are you today?"}))
        async with asyncio.timeout(10.0):
            async for message in ws:
                if isinstance(message, bytes):
                    first_audio = time.monotonic() - started
                    break
            else:
                pytest.fail("connection closed with no audio")
        assert first_audio < 3.0, f"TTS first audio took {first_audio:.2f}s"
    finally:
        await ws.close()


async def test_stt_finalizes_within_budget(config: Config) -> None:
    await _require_ws(config.stt_ws_url)
    sample_rate = 16_000
    # 1s of a quiet 220Hz tone — content doesn't matter, latency does.
    tone = bytes(
        int(3000 * math.sin(2 * math.pi * 220 * i / sample_rate)).to_bytes(
            2, "little", signed=True
        )[j]
        for i in range(sample_rate)
        for j in range(2)
    )
    ws = await websockets.connect(config.stt_ws_url)
    try:
        for offset in range(0, len(tone), 3200):
            await ws.send(tone[offset : offset + 3200])
        started = time.monotonic()
        await ws.send(json.dumps({"type": "end"}))
        async with asyncio.timeout(15.0):
            async for message in ws:
                if isinstance(message, str) and json.loads(message).get("type") == "final":
                    final_latency = time.monotonic() - started
                    break
            else:
                pytest.fail("connection closed with no final transcript")
        # Single end-of-utterance transcription (VEN-56): the final must be
        # quick — the old shape re-transcribed the whole buffer every 1s.
        assert final_latency < 5.0, f"STT finalize took {final_latency:.2f}s"
    finally:
        await ws.close()
