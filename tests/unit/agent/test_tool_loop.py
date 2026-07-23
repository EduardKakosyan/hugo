"""Streaming ToolLoop tests against a fake streaming LLM client — proves
sentence-by-sentence utterance emission, acknowledgment-before-tool
ordering, history accumulation, and error degradation, all with no server."""

from typing import Any

from hugo.agent.llm_client import AssistantTurn, ToolCallRequest
from hugo.agent.tool_loop import (
    ACKNOWLEDGMENTS,
    DEFAULT_SYSTEM_PROMPT,
    SentenceStream,
    ToolLoop,
    speechify,
)


def _turn(content: str = "", calls: list[ToolCallRequest] | None = None) -> AssistantTurn:
    return AssistantTurn(content=content, tool_calls=tuple(calls or []))


class _FakeStreamingLlm:
    """Each scripted pass is (content deltas, final AssistantTurn). The last
    pass repeats forever — lets a test script "always call a tool" with a
    single-item list."""

    def __init__(self, passes: list[tuple[list[str], AssistantTurn]]) -> None:
        self._passes = list(passes)
        self.seen_messages: list[list[Any]] = []
        self.seen_tools: list[Any] = []

    async def stream_with_tools(self, messages: Any, tools: Any) -> Any:
        self.seen_messages.append(list(messages))
        self.seen_tools.append(tools)
        deltas, turn = self._passes.pop(0) if len(self._passes) > 1 else self._passes[0]
        for delta in deltas:
            yield delta
        yield turn


class _FakeWebSearchTool:
    def __init__(self, result: str = "search result") -> None:
        self.result = result
        self.queries: list[str] = []

    async def search(self, query: str) -> str:
        self.queries.append(query)
        return self.result


async def _think_all(loop: ToolLoop, text: str) -> list[str]:
    return [utterance async for utterance in loop.think(text)]


async def test_reply_streams_out_sentence_by_sentence() -> None:
    llm = _FakeStreamingLlm(
        [(["Hel", "lo there. How", " are you"], _turn("Hello there. How are you"))]
    )
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    utterances = await _think_all(loop, "hi hugo")

    # First sentence is available before the stream ends; the unpunctuated
    # remainder still comes out at the end.
    assert utterances == ["Hello there.", "How are you"]


async def test_think_sends_system_prompt_then_user_turn() -> None:
    llm = _FakeStreamingLlm([(["hi there"], _turn("hi there"))])
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    await _think_all(loop, "what time is it")

    sent = llm.seen_messages[0]
    assert sent[0] == {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
    assert sent[1] == {"role": "user", "content": "what time is it"}


async def test_conversation_history_accumulates_across_turns() -> None:
    llm = _FakeStreamingLlm([(["ok."], _turn("ok.")), (["ok2."], _turn("ok2."))])
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    await _think_all(loop, "first question")
    await _think_all(loop, "second question")

    second_call_messages = llm.seen_messages[1]
    roles = [m["role"] for m in second_call_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert second_call_messages[2]["content"] == "ok."
    assert second_call_messages[3] == {"role": "user", "content": "second question"}


async def test_model_preamble_is_the_acknowledgment_for_a_tool_call() -> None:
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "weather"}')
    llm = _FakeStreamingLlm(
        [
            (["Let me search for that. "], _turn("Let me search for that. ", [call])),
            (["It's sunny."], _turn("It's sunny.")),
        ]
    )
    web_search = _FakeWebSearchTool(result="sunny today")
    loop = ToolLoop(llm, web_search=web_search)  # type: ignore[arg-type]

    utterances = await _think_all(loop, "what's the weather")

    # The model's own preamble was spoken (no canned phrase added), the
    # search ran, and the final answer followed.
    assert utterances == ["Let me search for that.", "It's sunny."]
    assert web_search.queries == ["weather"]
    second_call_messages = llm.seen_messages[1]
    tool_message = next(m for m in second_call_messages if m.get("role") == "tool")
    assert tool_message == {"role": "tool", "tool_call_id": "call_1", "content": "sunny today"}
    assistant_message = second_call_messages[2]
    assert assistant_message["tool_calls"][0]["function"]["name"] == "web_search"


async def test_silent_tool_call_gets_a_canned_acknowledgment() -> None:
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "weather"}')
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),  # no preamble at all
            (["It's sunny."], _turn("It's sunny.")),
        ]
    )
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    utterances = await _think_all(loop, "what's the weather")

    # Slow work is never silent (VEN-56): a canned acknowledgment precedes
    # the tool round-trip.
    assert utterances[0] in ACKNOWLEDGMENTS
    assert utterances[-1] == "It's sunny."


async def test_unknown_tool_reports_and_continues() -> None:
    call = ToolCallRequest(id="call_1", name="teleport", arguments="{}")
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),
            (["Can't do that."], _turn("Can't do that.")),
        ]
    )
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    utterances = await _think_all(loop, "teleport me")

    assert utterances[-1] == "Can't do that."
    tool_message = next(m for m in llm.seen_messages[1] if m.get("role") == "tool")
    assert "unknown tool" in tool_message["content"]


async def test_falls_back_after_max_tool_iterations() -> None:
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "x"}')
    llm = _FakeStreamingLlm([([], _turn(calls=[call]))])  # always calls a tool
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    utterances = await _think_all(loop, "loop forever")

    assert "trouble" in utterances[-1].lower()


async def test_llm_failure_degrades_to_a_spoken_apology() -> None:
    class _ExplodingLlm:
        async def stream_with_tools(self, messages: Any, tools: Any) -> Any:
            raise RuntimeError("boom")
            yield ""  # unreachable; makes this an async generator

    loop = ToolLoop(_ExplodingLlm(), web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    utterances = await _think_all(loop, "hi")

    assert len(utterances) == 1
    assert "sorry" in utterances[0].lower()


def test_sentence_stream_emits_at_boundaries_and_flushes_the_tail() -> None:
    stream = SentenceStream()
    assert stream.feed("Hello the") == []
    assert stream.feed("re. How are") == ["Hello there."]
    assert stream.feed(" you?\nGood.") == ["How are you?"]
    assert stream.flush() == "Good."
    assert stream.flush() == ""


def test_speechify_strips_markdown_and_bullets() -> None:
    assert speechify("**Bold** and `code` and #tag") == "Bold and code and tag"
    assert (
        speechify("Here you go:\n- first thing\n- second thing\n1. third")
        == "Here you go: first thing second thing third"
    )
    assert speechify("  plain sentence stays put.  ") == "plain sentence stays put."
