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


class _StubWebSearch:
    """Real Tavily isn't under test (and needs a key); the LLM+ToolLoop
    behavior is."""

    async def search(self, query: str) -> str:
        return f"stub result for: {query}"


async def test_live_reply_to_what_can_you_do_sounds_like_a_person(config: Config) -> None:
    """The live conversational-quality check (VEN-56): the reply to a
    trivial question must be a short spoken-register answer — not the
    reasoning trace, not a recitation of the system prompt, not markdown —
    and its first utterance must arrive in conversational time. Runs
    entirely in code: no mic, no speaker, no human."""
    await _require_llm(config)
    from hugo.agent.tool_loop import ToolLoop

    llm = LlmClient(base_url=config.llm_base_url, model=config.llm_model)
    loop = ToolLoop(llm, web_search=_StubWebSearch())  # type: ignore[arg-type]

    started = time.monotonic()
    first_utterance_at: float | None = None
    utterances: list[str] = []
    async for utterance in loop.think("What can you do?"):
        if first_utterance_at is None:
            first_utterance_at = time.monotonic() - started
        utterances.append(utterance)
    total_s = time.monotonic() - started

    reply = " ".join(utterances)
    print(f"\nreply ({first_utterance_at:.2f}s to first utterance, {total_s:.2f}s total): {reply}")

    assert reply.strip(), "empty reply"
    # Spoken register: speechify strips markdown, but the model shouldn't
    # be producing it in the first place with the voice system prompt.
    assert not any(token in reply for token in ("**", "##", "```", "http://", "https://"))
    # Not the reasoning trace: the classic trace tells that were being
    # spoken aloud before the reasoning parser was configured.
    lowered = reply.lower()
    for trace_tell in ("<think", "the user asks", "the user wants", "we need to respond"):
        assert trace_tell not in lowered, f"reasoning-trace tell in spoken reply: {trace_tell!r}"
    # Not parroting its own instructions (distinctive system-prompt span).
    assert "no bullet points" not in lowered
    # Short enough to be a spoken answer, not an essay.
    assert len(reply.split()) < 120, f"reply too long to speak: {len(reply.split())} words"
    # Conversational: the PRD budget is ~3s to first *audio*; the text
    # feeding it must arrive faster still. 8s is the generous ceiling
    # before this fails as a regression.
    assert first_utterance_at is not None and first_utterance_at < 8.0


async def test_full_cascade_round_trip_no_human_required(config: Config) -> None:
    """The whole cascade in code (VEN-56): TTS speaks 'What can you do?',
    STT transcribes that audio back, the LLM answers the transcript —
    proving the three real models actually compose, with no human and no
    robot in the loop."""
    await _require_llm(config)
    await _require_ws(config.tts_ws_url)
    await _require_ws(config.stt_ws_url)
    from hugo.agent.tool_loop import ToolLoop
    from hugo.voice.loop import normalize_command
    from hugo.voice.resample import StreamingPcm16Resampler
    from hugo.voice.stt import SttClient
    from hugo.voice.tts import TtsClient

    # 1. HUGO's own voice asks the question.
    tts = TtsClient(config.tts_ws_url)
    spoken_pcm = b""
    async for chunk in tts.speak("What can you do?"):
        spoken_pcm += chunk
    assert len(spoken_pcm) > 0, "TTS produced no audio"

    # 2. The robot's mic runs at 16kHz — resample exactly as the loop does.
    resampler = StreamingPcm16Resampler(config.tts_sample_rate_hz, 16_000)
    mic_pcm = resampler.process(spoken_pcm)

    # 3. STT hears it.
    async with SttClient(config.stt_ws_url) as stt:
        for offset in range(0, len(mic_pcm), 3200):
            await stt.send_audio(mic_pcm[offset : offset + 3200])
        await stt.end_utterance()
        transcript = ""
        async for t in stt.transcripts():
            if t.kind == "final":
                transcript = t.text
    print(f"\ncascade transcript: {transcript!r}")
    assert "what can you do" in normalize_command(transcript), (
        f"STT did not recover the spoken question: {transcript!r}"
    )

    # 4. The LLM answers what STT heard.
    llm = LlmClient(base_url=config.llm_base_url, model=config.llm_model)
    loop = ToolLoop(llm, web_search=_StubWebSearch())  # type: ignore[arg-type]
    utterances = [u async for u in loop.think(transcript)]
    reply = " ".join(utterances)
    print(f"cascade reply: {reply}")
    assert reply.strip()
    assert "sorry" not in reply.lower() or "problem" not in reply.lower(), (
        "cascade degraded to the failure apology"
    )


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
