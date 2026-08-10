"""Tests WebSearchTool against a fake httpx.AsyncClient (same shape as
test_orchestrator.py's fake, extended with .post()/.json()/raise_for_status())
-- no real network call. search() is the Tavily call; invoke() is the Tool
seam over it, where httpx exceptions become ToolFailures the model reads."""

from typing import Any

import httpx
import pytest

from hugo.agent.tools import ToolFailure
from hugo.agent.tools.web_search import WebSearchTool, _format_results


class _FakeHttpResponse:
    def __init__(self, status_code: int, json_data: dict[str, Any]) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=None,  # type: ignore[arg-type]
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self._json_data


class _FakeHttpClient:
    def __init__(
        self,
        response: _FakeHttpResponse,
        calls: list[dict[str, Any]],
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._calls = calls
        self._error = error

    async def __aenter__(self) -> "_FakeHttpClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeHttpResponse:
        self._calls.append({"url": url, "json": json})
        if self._error is not None:
            raise self._error
        return self._response


def _install(
    monkeypatch: pytest.MonkeyPatch,
    response: _FakeHttpResponse,
    calls: list[dict[str, Any]] | None = None,
    error: Exception | None = None,
) -> None:
    monkeypatch.setattr(
        "hugo.agent.tools.web_search.httpx.AsyncClient",
        lambda **_kwargs: _FakeHttpClient(response, calls if calls is not None else [], error),
    )


def _assert_speakable(text: str) -> None:
    """Failure text is read by a model that will paraphrase it aloud, so it
    must carry nothing internal: no exception class names, no URLs, no
    status codes (agent/tools/__init__.py, CONTEXT.md)."""
    assert not any(character.isdigit() for character in text), f"status code leaked: {text!r}"
    assert "http" not in text.lower(), f"URL leaked: {text!r}"
    for class_tell in ("Error", "Exception", "httpx", "Timeout"):
        assert class_tell not in text, f"exception class name leaked: {text!r}"


def test_format_results_includes_answer_and_results() -> None:
    data = {
        "answer": "It's sunny.",
        "results": [{"title": "Weather", "content": "Sunny today.", "url": "http://x.test"}],
    }

    formatted = _format_results(data)

    assert "It's sunny." in formatted
    assert "Weather: Sunny today. (http://x.test)" in formatted


def test_format_results_without_answer() -> None:
    data = {"results": [{"title": "T", "content": "C", "url": "http://x.test"}]}

    formatted = _format_results(data)

    assert formatted == "T: C (http://x.test)"


def test_format_results_empty() -> None:
    assert _format_results({"results": []}) == "No results found."


def test_schema_is_flat_with_no_refs() -> None:
    """Generated from a flat pydantic model on purpose: $defs/$ref are not
    reliably handled downstream (agent/tools/__init__.py::schema_from)."""
    schema = WebSearchTool.schema

    assert schema["function"]["name"] == "web_search"
    parameters = schema["function"]["parameters"]
    assert parameters["type"] == "object"
    assert parameters["required"] == ["query"]
    assert "query" in parameters["properties"]  # type: ignore[operator]
    assert "$defs" not in parameters and "$ref" not in repr(parameters)
    # pydantic's generated titles carry Python class/field names into the
    # prompt; the hand-written schema this replaces had none.
    assert "title" not in repr(parameters)


async def test_search_calls_tavily_and_formats_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    _install(monkeypatch, _FakeHttpResponse(200, {"answer": "42", "results": []}), calls)
    tool = WebSearchTool(api_key="test-key")

    result = await tool.search("the answer to everything")

    assert result == "42"
    assert calls[0]["url"] == "https://api.tavily.com/search"
    assert calls[0]["json"]["api_key"] == "test-key"
    assert calls[0]["json"]["query"] == "the answer to everything"


async def test_search_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeHttpResponse(401, {}))
    tool = WebSearchTool(api_key="bad-key")

    with pytest.raises(httpx.HTTPError):
        await tool.search("query")


async def test_invoke_returns_the_formatted_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeHttpResponse(200, {"answer": "42", "results": []}))
    tool = WebSearchTool(api_key="test-key")

    assert await tool.invoke({"query": "the answer to everything"}) == "42"


async def test_invoke_marks_a_timeout_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        _FakeHttpResponse(200, {}),
        error=httpx.ReadTimeout("timed out"),
    )
    tool = WebSearchTool(api_key="test-key")

    result = await tool.invoke({"query": "weather"})

    assert isinstance(result, ToolFailure)
    assert result.retryable
    _assert_speakable(result.text)


async def test_invoke_marks_a_rejected_key_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected credential fails identically three times — retrying it
    only costs the user ten seconds before the same bad news."""
    _install(monkeypatch, _FakeHttpResponse(401, {}))
    tool = WebSearchTool(api_key="bad-key")

    result = await tool.invoke({"query": "weather"})

    assert isinstance(result, ToolFailure)
    assert not result.retryable
    _assert_speakable(result.text)


async def test_invoke_marks_a_server_fault_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeHttpResponse(503, {}))
    tool = WebSearchTool(api_key="test-key")

    result = await tool.invoke({"query": "weather"})

    assert isinstance(result, ToolFailure)
    assert result.retryable
    _assert_speakable(result.text)


async def test_invoke_reports_missing_arguments_without_calling_tavily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _install(monkeypatch, _FakeHttpResponse(200, {}), calls)
    tool = WebSearchTool(api_key="test-key")

    result = await tool.invoke({})

    assert isinstance(result, ToolFailure)
    assert not result.retryable
    assert "query" in result.text
    assert calls == []
