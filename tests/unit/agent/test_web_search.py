"""Tests WebSearchTool against a fake httpx.AsyncClient (same shape as
test_orchestrator.py's fake, extended with .post()/.json()/raise_for_status())
-- no real network call."""

from typing import Any

import httpx
import pytest

from hugo.agent.web_search import WebSearchTool, _format_results


class _FakeHttpResponse:
    def __init__(self, status_code: int, json_data: dict[str, Any]) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict[str, Any]:
        return self._json_data


class _FakeHttpClient:
    def __init__(self, response: _FakeHttpResponse, calls: list[dict[str, Any]]) -> None:
        self._response = response
        self._calls = calls

    async def __aenter__(self) -> "_FakeHttpClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeHttpResponse:
        self._calls.append({"url": url, "json": json})
        return self._response


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


async def test_search_calls_tavily_and_formats_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    response = _FakeHttpResponse(200, {"answer": "42", "results": []})
    monkeypatch.setattr(
        "hugo.agent.web_search.httpx.AsyncClient",
        lambda **_kwargs: _FakeHttpClient(response, calls),
    )
    tool = WebSearchTool(api_key="test-key")

    result = await tool.search("the answer to everything")

    assert result == "42"
    assert calls[0]["url"] == "https://api.tavily.com/search"
    assert calls[0]["json"]["api_key"] == "test-key"
    assert calls[0]["json"]["query"] == "the answer to everything"


async def test_search_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeHttpResponse(401, {})
    monkeypatch.setattr(
        "hugo.agent.web_search.httpx.AsyncClient",
        lambda **_kwargs: _FakeHttpClient(response, []),
    )
    tool = WebSearchTool(api_key="bad-key")

    with pytest.raises(httpx.HTTPError):
        await tool.search("query")
