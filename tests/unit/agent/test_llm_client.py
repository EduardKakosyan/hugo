"""Tests LlmClient against a fake AsyncOpenAI matching the real SDK's
streaming chunk shape (chunk.choices[0].delta with content and tool_calls
fragments) — no real server."""

from typing import Any

import pytest

from hugo.agent.llm_client import AssistantTurn, LlmClient, ToolCallRequest


class _FakeFunctionFragment:
    def __init__(self, name: str | None, arguments: str | None) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCallFragment:
    def __init__(
        self,
        index: int,
        id: str | None = None,
        name: str | None = None,
        arguments: str | None = None,
    ) -> None:
        self.index = index
        self.id = id
        self.function = _FakeFunctionFragment(name, arguments)


class _FakeDelta:
    def __init__(
        self, content: str | None, tool_calls: list[_FakeToolCallFragment] | None = None
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, delta: _FakeDelta) -> None:
        self.delta = delta


class _FakeChunk:
    def __init__(self, delta: _FakeDelta | None) -> None:
        self.choices = [] if delta is None else [_FakeChoice(delta)]


class _FakeStream:
    def __init__(self, chunks: list[_FakeChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> "_FakeStream":
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> _FakeChunk:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeCompletions:
    def __init__(self, chunks: list[_FakeChunk], calls: list[dict[str, Any]]) -> None:
        self._chunks = chunks
        self._calls = calls

    async def create(self, **kwargs: Any) -> _FakeStream:
        self._calls.append(kwargs)
        return _FakeStream(self._chunks)


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeAsyncOpenAI:
    def __init__(self, chunks: list[_FakeChunk], calls: list[dict[str, Any]]) -> None:
        self.chat = _FakeChat(_FakeCompletions(chunks, calls))


def _patch_openai(
    monkeypatch: pytest.MonkeyPatch, chunks: list[_FakeChunk]
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "hugo.agent.llm_client.AsyncOpenAI",
        lambda **_kwargs: _FakeAsyncOpenAI(chunks, calls),
    )
    return calls


def _content_chunks(*parts: str | None) -> list[_FakeChunk]:
    return [_FakeChunk(_FakeDelta(part)) for part in parts]


async def test_stream_yields_only_non_empty_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch, _content_chunks("Hel", "lo", " there", None))
    client = LlmClient(base_url="http://fake", model="test-model")

    parts = [d async for d in client.stream([{"role": "user", "content": "hi"}])]

    assert parts == ["Hel", "lo", " there"]


async def test_complete_joins_stream_into_one_string(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch, _content_chunks("Hel", "lo", " there", None))
    client = LlmClient(base_url="http://fake", model="test-model")

    result = await client.complete([{"role": "user", "content": "hi"}])

    assert result == "Hello there"


async def test_complete_passes_model_stream_flag_and_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_openai(monkeypatch, _content_chunks("hi"))
    client = LlmClient(base_url="http://fake", model="my-model")

    await client.complete([{"role": "user", "content": "hi"}])

    assert calls[0]["model"] == "my-model"
    assert calls[0]["stream"] is True
    # Nemotron 3's model-card recommended sampling, applied everywhere.
    assert calls[0]["temperature"] == 1.0
    assert calls[0]["top_p"] == 0.95


async def _collect(client: LlmClient) -> tuple[list[str], AssistantTurn]:
    deltas: list[str] = []
    turn: AssistantTurn | None = None
    async for item in client.stream_with_tools([{"role": "user", "content": "hi"}], tools=[]):
        if isinstance(item, AssistantTurn):
            turn = item
        else:
            deltas.append(item)
    assert turn is not None
    return deltas, turn


async def test_stream_with_tools_yields_deltas_then_one_assembled_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openai(monkeypatch, _content_chunks("It's ", "sunny.", None))
    client = LlmClient(base_url="http://fake", model="test-model")

    deltas, turn = await _collect(client)

    assert deltas == ["It's ", "sunny."]
    assert turn == AssistantTurn(content="It's sunny.", tool_calls=())


async def test_stream_with_tools_accumulates_tool_call_fragments_by_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        _FakeChunk(_FakeDelta("Checking. ")),
        _FakeChunk(
            _FakeDelta(
                None,
                [_FakeToolCallFragment(index=0, id="call_1", name="web_search", arguments='{"que')],
            )
        ),
        _FakeChunk(_FakeDelta(None, [_FakeToolCallFragment(index=0, arguments='ry": "x"}')])),
        _FakeChunk(None),  # e.g. a final usage-only chunk with no choices
    ]
    _patch_openai(monkeypatch, chunks)
    client = LlmClient(base_url="http://fake", model="test-model")

    deltas, turn = await _collect(client)

    assert deltas == ["Checking. "]
    assert turn.content == "Checking. "
    assert turn.tool_calls == (
        ToolCallRequest(id="call_1", name="web_search", arguments='{"query": "x"}'),
    )


async def test_stream_with_tools_passes_tools_and_stream_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_openai(monkeypatch, _content_chunks("ok"))
    client = LlmClient(base_url="http://fake", model="my-model")
    tools: list[Any] = [{"type": "function", "function": {"name": "web_search"}}]

    async for _ in client.stream_with_tools([{"role": "user", "content": "hi"}], tools=tools):
        pass

    assert calls[0]["model"] == "my-model"
    assert calls[0]["tools"] == tools
    assert calls[0]["stream"] is True


async def test_stream_with_tools_omits_an_empty_tools_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # vLLM 0.25 rejects `tools: []` with a 400 — found live on dgx1.
    from openai import NOT_GIVEN

    calls = _patch_openai(monkeypatch, _content_chunks("ok"))
    client = LlmClient(base_url="http://fake", model="my-model")

    async for _ in client.stream_with_tools([{"role": "user", "content": "hi"}], tools=[]):
        pass

    assert calls[0]["tools"] is NOT_GIVEN


def test_assistant_turn_message_param_includes_tool_calls() -> None:
    turn = AssistantTurn(
        content="Checking.",
        tool_calls=(ToolCallRequest(id="call_1", name="web_search", arguments="{}"),),
    )

    message = turn.as_message_param()

    assert message == {
        "role": "assistant",
        "content": "Checking.",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": "{}"},
            }
        ],
    }


def test_assistant_turn_message_param_omits_empty_content() -> None:
    turn = AssistantTurn(
        content="", tool_calls=(ToolCallRequest(id="c", name="web_search", arguments="{}"),)
    )

    message = turn.as_message_param()

    assert "content" not in message
