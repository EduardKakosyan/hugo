"""Streaming ToolLoop tests against a fake streaming LLM client — proves
sentence-by-sentence utterance emission, the acknowledgment racing the tool,
history accumulation, and error degradation, all with no server."""

import asyncio
from typing import Any

from openai.types.chat import ChatCompletionToolParam

from hugo.agent.llm_client import AssistantTurn, ToolCallRequest
from hugo.agent.tool_loop import (
    ACKNOWLEDGMENTS,
    DEFAULT_SYSTEM_PROMPT,
    SentenceStream,
    ToolLoop,
    speechify,
)
from hugo.agent.tools import ToolFailure


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


# Shrinks the acknowledgment race to a sub-millisecond window, the same
# trick _build_loop uses on the voice loop's timing — a scripted delay beats
# waiting out a real second.
_ACK_AFTER_S = 0.01
_SLOWER_THAN_THE_RACE_S = 0.05


class _FakeTool:
    """Satisfies the Tool Protocol structurally — no subclassing, the same
    convention as tests/unit/voice/fakes.py. Records the argument dicts it
    was invoked with, and `delay` scripts latency so the acknowledgment race
    is deterministic (as FakeThinker.delay_before_each does for the nudge)."""

    def __init__(
        self,
        name: str = "web_search",
        result: str | ToolFailure = "search result",
        delay: float = 0.0,
    ) -> None:
        self.schema: ChatCompletionToolParam = {
            "type": "function",
            "function": {
                "name": name,
                "description": f"fake {name}",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        self.calls: list[dict[str, Any]] = []
        self._result = result
        self._delay = delay

    async def invoke(self, arguments: dict[str, Any]) -> str | ToolFailure:
        self.calls.append(arguments)
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


async def _think_all(loop: ToolLoop, text: str) -> list[str]:
    return [utterance async for utterance in loop.think(text)]


def _acknowledgments(utterances: list[str]) -> list[str]:
    return [utterance for utterance in utterances if utterance in ACKNOWLEDGMENTS]


async def test_reply_streams_out_sentence_by_sentence() -> None:
    llm = _FakeStreamingLlm(
        [(["Hel", "lo there. How", " are you"], _turn("Hello there. How are you"))]
    )
    loop = ToolLoop(llm, tools=[_FakeTool()])

    utterances = await _think_all(loop, "hi hugo")

    # First sentence is available before the stream ends; the unpunctuated
    # remainder still comes out at the end.
    assert utterances == ["Hello there.", "How are you"]


async def test_think_sends_system_prompt_then_user_turn() -> None:
    llm = _FakeStreamingLlm([(["hi there"], _turn("hi there"))])
    loop = ToolLoop(llm, tools=[_FakeTool()])

    await _think_all(loop, "what time is it")

    sent = llm.seen_messages[0]
    assert sent[0] == {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
    assert sent[1] == {"role": "user", "content": "what time is it"}


async def test_every_tools_schema_is_offered_to_the_model() -> None:
    """The loop names no tool: it sends whatever the collection carries."""
    llm = _FakeStreamingLlm([(["ok."], _turn("ok."))])
    loop = ToolLoop(llm, tools=[_FakeTool("web_search"), _FakeTool("get_current_time")])

    await _think_all(loop, "hi")

    offered = [schema["function"]["name"] for schema in llm.seen_tools[0]]
    assert offered == ["web_search", "get_current_time"]


async def test_conversation_history_accumulates_across_turns() -> None:
    llm = _FakeStreamingLlm([(["ok."], _turn("ok.")), (["ok2."], _turn("ok2."))])
    loop = ToolLoop(llm, tools=[_FakeTool()])

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
    web_search = _FakeTool(result="sunny today")
    loop = ToolLoop(llm, tools=[web_search])

    utterances = await _think_all(loop, "what's the weather")

    # The model's own preamble was spoken (no canned phrase added), the
    # search ran, and the final answer followed.
    assert utterances == ["Let me search for that.", "It's sunny."]
    assert web_search.calls == [{"query": "weather"}]
    second_call_messages = llm.seen_messages[1]
    tool_message = next(m for m in second_call_messages if m.get("role") == "tool")
    assert tool_message == {"role": "tool", "tool_call_id": "call_1", "content": "sunny today"}
    assistant_message = second_call_messages[2]
    assert assistant_message["tool_calls"][0]["function"]["name"] == "web_search"


async def test_a_tool_that_returns_fast_is_never_announced() -> None:
    """The acknowledgment races the tool instead of firing structurally: with
    tools that return in microseconds, a canned phrase would be the only slow
    thing in the turn (docs/adr/0006)."""
    call = ToolCallRequest(id="call_1", name="get_current_time", arguments="{}")
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),  # no preamble at all
            (["It's Sunday."], _turn("It's Sunday.")),
        ]
    )
    tool = _FakeTool("get_current_time", result="Sunday, 10 August 2026")
    loop = ToolLoop(llm, tools=[tool], acknowledge_after_s=_ACK_AFTER_S)

    utterances = await _think_all(loop, "what day is it")

    assert utterances == ["It's Sunday."]
    assert tool.calls == [{}]


async def test_a_slow_tool_gets_one_acknowledgment_before_the_answer() -> None:
    """Silence is the intolerable failure, so work that outlasts the window
    is announced — once, ahead of the answer it's covering for."""
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "weather"}')
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),
            (["It's sunny."], _turn("It's sunny.")),
        ]
    )
    loop = ToolLoop(
        llm,
        tools=[_FakeTool(delay=_SLOWER_THAN_THE_RACE_S)],
        acknowledge_after_s=_ACK_AFTER_S,
    )

    utterances = await _think_all(loop, "what's the weather")

    assert utterances[0] in ACKNOWLEDGMENTS
    assert utterances[-1] == "It's sunny."
    assert len(_acknowledgments(utterances)) == 1


async def test_two_slow_calls_in_one_turn_still_draw_only_one_acknowledgment() -> None:
    calls = [
        ToolCallRequest(id="call_1", name="get_current_time", arguments="{}"),
        ToolCallRequest(id="call_2", name="web_search", arguments='{"query": "weather"}'),
    ]
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=calls)),
            (["It's sunny today."], _turn("It's sunny today.")),
        ]
    )
    loop = ToolLoop(
        llm,
        tools=[
            _FakeTool("get_current_time", result="Sunday", delay=_SLOWER_THAN_THE_RACE_S),
            _FakeTool("web_search", delay=_SLOWER_THAN_THE_RACE_S),
        ],
        acknowledge_after_s=_ACK_AFTER_S,
    )

    utterances = await _think_all(loop, "what's the weather today")

    assert len(_acknowledgments(utterances)) == 1


async def test_a_chain_across_two_passes_is_announced_once_not_hop_by_hop() -> None:
    """`acknowledged` is per turn, not per pass: "what did I say I'd do
    today" checks the date and then the notes, and that is still one question
    from the user's side."""
    time_call = ToolCallRequest(id="call_1", name="get_current_time", arguments="{}")
    recall_call = ToolCallRequest(id="call_2", name="recall_facts", arguments='{"query": "today"}')
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[time_call])),
            ([], _turn(calls=[recall_call])),
            (["You said you'd call the dentist."], _turn("You said you'd call the dentist.")),
        ]
    )
    loop = ToolLoop(
        llm,
        tools=[
            _FakeTool("get_current_time", result="Sunday", delay=_SLOWER_THAN_THE_RACE_S),
            _FakeTool("recall_facts", result="call the dentist", delay=_SLOWER_THAN_THE_RACE_S),
        ],
        acknowledge_after_s=_ACK_AFTER_S,
    )

    utterances = await _think_all(loop, "what did I say I'd do today")

    assert len(_acknowledgments(utterances)) == 1
    assert utterances[-1] == "You said you'd call the dentist."


async def test_a_model_preamble_suppresses_the_canned_phrase_even_when_slow() -> None:
    """Anything the model said ahead of the call IS the acknowledgment, so a
    volunteered preamble loses nothing by the phrases being generic."""
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "weather"}')
    llm = _FakeStreamingLlm(
        [
            (["Checking the forecast. "], _turn("Checking the forecast. ", [call])),
            (["It's sunny."], _turn("It's sunny.")),
        ]
    )
    loop = ToolLoop(
        llm,
        tools=[_FakeTool(delay=_SLOWER_THAN_THE_RACE_S)],
        acknowledge_after_s=_ACK_AFTER_S,
    )

    utterances = await _think_all(loop, "what's the weather")

    assert utterances == ["Checking the forecast.", "It's sunny."]


async def test_unknown_tool_reports_and_continues() -> None:
    call = ToolCallRequest(id="call_1", name="teleport", arguments="{}")
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),
            (["Can't do that."], _turn("Can't do that.")),
        ]
    )
    loop = ToolLoop(llm, tools=[])

    utterances = await _think_all(loop, "teleport me")

    assert utterances[-1] == "Can't do that."
    tool_message = next(m for m in llm.seen_messages[1] if m.get("role") == "tool")
    assert "no tool called teleport" in tool_message["content"]


async def test_malformed_arguments_are_reported_to_the_model() -> None:
    """vLLM takes the unconstrained tool_choice="auto" path, so arguments
    reach the loop unvalidated and really can be broken JSON."""
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": ')
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),
            (["Let me try again differently."], _turn("Let me try again differently.")),
        ]
    )
    web_search = _FakeTool()
    loop = ToolLoop(llm, tools=[web_search])

    await _think_all(loop, "what's the weather")

    tool_message = next(m for m in llm.seen_messages[1] if m.get("role") == "tool")
    assert "weren't valid JSON" in tool_message["content"]
    assert web_search.calls == []


async def test_tool_failure_text_reaches_the_model_as_the_tool_result() -> None:
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "weather"}')
    llm = _FakeStreamingLlm(
        [
            ([], _turn(calls=[call])),
            (["I couldn't reach search."], _turn("I couldn't reach search.")),
        ]
    )
    failure = ToolFailure("the web search service didn't answer.", retryable=True)
    loop = ToolLoop(llm, tools=[_FakeTool(result=failure)])

    await _think_all(loop, "what's the weather")

    tool_message = next(m for m in llm.seen_messages[1] if m.get("role") == "tool")
    assert tool_message["content"] == failure.text


async def test_falls_back_after_max_tool_iterations() -> None:
    call = ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "x"}')
    llm = _FakeStreamingLlm([([], _turn(calls=[call]))])  # always calls a tool
    loop = ToolLoop(llm, tools=[_FakeTool()])

    utterances = await _think_all(loop, "loop forever")

    assert "trouble" in utterances[-1].lower()


async def test_llm_failure_degrades_to_a_spoken_apology() -> None:
    class _ExplodingLlm:
        async def stream_with_tools(self, messages: Any, tools: Any) -> Any:
            raise RuntimeError("boom")
            yield ""  # unreachable; makes this an async generator

    loop = ToolLoop(_ExplodingLlm(), tools=[_FakeTool()])

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


async def test_mood_tag_is_stripped_reported_and_never_spoken() -> None:
    moods: list[str] = []
    llm = _FakeStreamingLlm(
        [(["[cheerful] Grea", "t news. It works."], _turn("[cheerful] Great news. It works."))]
    )
    loop = ToolLoop(llm, tools=[_FakeTool()], on_mood=moods.append)

    utterances = await _think_all(loop, "did it work")

    # The tag steers body language and must NEVER reach TTS — the same
    # discipline as reasoning traces.
    assert utterances == ["Great news.", "It works."]
    assert moods == ["cheerful"]


async def test_untagged_reply_speaks_unchanged_with_no_mood_report() -> None:
    moods: list[str] = []
    llm = _FakeStreamingLlm([(["Plain answer."], _turn("Plain answer."))])
    loop = ToolLoop(llm, tools=[_FakeTool()], on_mood=moods.append)

    assert await _think_all(loop, "hi") == ["Plain answer."]
    assert moods == []


async def test_tag_on_its_own_line_is_not_spoken_as_an_empty_utterance() -> None:
    moods: list[str] = []
    llm = _FakeStreamingLlm(
        [(["[thoughtful]\n", "Well, maybe."], _turn("[thoughtful]\nWell, maybe."))]
    )
    loop = ToolLoop(llm, tools=[_FakeTool()], on_mood=moods.append)

    assert await _think_all(loop, "hmm") == ["Well, maybe."]
    assert moods == ["thoughtful"]


async def test_mood_callback_failure_never_breaks_speech() -> None:
    def boom(mood: str) -> None:
        raise RuntimeError("motion layer exploded")

    llm = _FakeStreamingLlm([(["[excited] Yes."], _turn("[excited] Yes."))])
    loop = ToolLoop(llm, tools=[_FakeTool()], on_mood=boom)

    assert await _think_all(loop, "hi") == ["Yes."]
