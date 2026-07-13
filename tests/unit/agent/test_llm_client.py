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
