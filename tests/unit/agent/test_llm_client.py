"""Tests LlmClient against a fake AsyncOpenAI matching the real SDK's
streaming chunk shape (chunk.choices[0].delta.content) — no real server."""

from typing import Any

import pytest

from hugo.agent.llm_client import LlmClient


class _FakeDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeStream:
    def __init__(self, deltas: list[str | None]) -> None:
        self._deltas = deltas

    def __aiter__(self) -> "_FakeStream":
        self._iter = iter(self._deltas)
        return self

    async def __anext__(self) -> _FakeChunk:
        try:
            return _FakeChunk(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeCompletions:
    def __init__(self, deltas: list[str | None], calls: list[dict[str, Any]]) -> None:
        self._deltas = deltas
        self._calls = calls

    async def create(self, **kwargs: Any) -> _FakeStream:
        self._calls.append(kwargs)
        return _FakeStream(self._deltas)


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeAsyncOpenAI:
    def __init__(self, deltas: list[str | None], calls: list[dict[str, Any]]) -> None:
        self.chat = _FakeChat(_FakeCompletions(deltas, calls))


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str | None], list[dict[str, Any]]]:
    deltas: list[str | None] = ["Hel", "lo", " there", None]  # a None delta, like real usage tokens
    calls: list[dict[str, Any]] = []

    def factory(**_kwargs: Any) -> _FakeAsyncOpenAI:
        return _FakeAsyncOpenAI(deltas, calls)

    monkeypatch.setattr("hugo.agent.llm_client.AsyncOpenAI", factory)
    return deltas, calls


async def test_stream_yields_only_non_empty_deltas(
    fake_openai: tuple[list[str | None], list[dict[str, Any]]],
) -> None:
    client = LlmClient(base_url="http://fake", model="test-model")

    parts = [d async for d in client.stream([{"role": "user", "content": "hi"}])]

    assert parts == ["Hel", "lo", " there"]


async def test_complete_joins_stream_into_one_string(
    fake_openai: tuple[list[str | None], list[dict[str, Any]]],
) -> None:
    client = LlmClient(base_url="http://fake", model="test-model")

    result = await client.complete([{"role": "user", "content": "hi"}])

    assert result == "Hello there"


async def test_complete_passes_model_and_stream_flag(
    fake_openai: tuple[list[str | None], list[dict[str, Any]]],
) -> None:
    _deltas, calls = fake_openai
    client = LlmClient(base_url="http://fake", model="my-model")

    await client.complete([{"role": "user", "content": "hi"}])

    assert calls[0]["model"] == "my-model"
    assert calls[0]["stream"] is True


class _FakeMessage:
    def __init__(self, content: str | None, tool_calls: list[Any] | None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _FakeCompletionChoice:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class _FakeCompletionResponse:
    def __init__(self, message: _FakeMessage) -> None:
        self.choices = [_FakeCompletionChoice(message)]


class _FakeToolCompletions:
    def __init__(self, message: _FakeMessage, calls: list[dict[str, Any]]) -> None:
        self._message = message
        self._calls = calls

    async def create(self, **kwargs: Any) -> _FakeCompletionResponse:
        self._calls.append(kwargs)
        return _FakeCompletionResponse(self._message)


class _FakeToolChat:
    def __init__(self, completions: _FakeToolCompletions) -> None:
        self.completions = completions


class _FakeToolAsyncOpenAI:
    def __init__(self, message: _FakeMessage, calls: list[dict[str, Any]]) -> None:
        self.chat = _FakeToolChat(_FakeToolCompletions(message, calls))


def _patch_openai_for_tools(
    monkeypatch: pytest.MonkeyPatch, message: _FakeMessage
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "hugo.agent.llm_client.AsyncOpenAI",
        lambda **_kwargs: _FakeToolAsyncOpenAI(message, calls),
    )
    return calls


async def test_complete_with_tools_returns_plain_content_when_no_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _FakeMessage(content="hello!", tool_calls=None)
    _patch_openai_for_tools(monkeypatch, message)
    client = LlmClient(base_url="http://fake", model="test-model")

    result = await client.complete_with_tools([{"role": "user", "content": "hi"}], tools=[])

    assert result.content == "hello!"
    assert result.tool_calls is None


async def test_complete_with_tools_returns_tool_calls_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tool_call = object()
    message = _FakeMessage(content=None, tool_calls=[fake_tool_call])
    _patch_openai_for_tools(monkeypatch, message)
    client = LlmClient(base_url="http://fake", model="test-model")

    result = await client.complete_with_tools([{"role": "user", "content": "hi"}], tools=[])

    assert result.tool_calls == [fake_tool_call]


async def test_complete_with_tools_passes_model_and_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _FakeMessage(content="ok", tool_calls=None)
    calls = _patch_openai_for_tools(monkeypatch, message)
    client = LlmClient(base_url="http://fake", model="my-model")
    tools: list[Any] = [{"type": "function", "function": {"name": "web_search"}}]

    await client.complete_with_tools([{"role": "user", "content": "hi"}], tools=tools)

    assert calls[0]["model"] == "my-model"
    assert calls[0]["tools"] == tools
    assert "stream" not in calls[0]
