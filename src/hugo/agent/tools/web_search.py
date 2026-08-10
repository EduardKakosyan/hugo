"""Web search, backed by Tavily's REST API (https://tavily.com) -- chosen
for its free tier and JSON responses shaped for LLM tool results, not raw
HTML/SERP data. No SDK dependency: a single POST is simple enough to do
directly with httpx, which is already a core dependency.

`search()` stays public because `hugo dev search` drives it directly as a
Tavily diagnostic. `invoke()` is the Tool seam around it, and is the only
place httpx's vocabulary is read: classification is the tool's job, so the
dispatch layer never learns what an httpx exception is (agent/tools).
"""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from hugo.agent.tools import ToolFailure, parse_args, schema_from

TAVILY_API_URL = "https://api.tavily.com/search"

# Worth another attempt: overload, rate limiting, and server-side faults
# plausibly go differently in a second. A rejected key or a malformed
# request will fail identically three times and just cost the user ten
# seconds before the same bad news.
_RETRYABLE_STATUS_CODES = frozenset({408, 429})


class WebSearchArgs(BaseModel):
    query: str = Field(description="The search query, as concise natural-language or keywords.")


class WebSearchTool:
    schema = schema_from(
        "web_search",
        "Search the web for current information, facts, or anything not in "
        "your training data -- recent events, real-time data, or anything "
        "you're not confident about.",
        WebSearchArgs,
    )

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def invoke(self, arguments: dict[str, Any]) -> str | ToolFailure:
        args = parse_args(WebSearchArgs, arguments)
        if isinstance(args, ToolFailure):
            return args
        try:
            return await self.search(args.query)
        except httpx.HTTPStatusError as exc:
            return _status_failure(exc.response.status_code)
        except httpx.HTTPError:
            # Timeouts and connect/read errors both land here — the network
            # or the service was unreachable, which is exactly the failure
            # a retry exists for.
            return ToolFailure("the web search service didn't answer.", retryable=True)
        except (ValueError, KeyError, TypeError):
            # A body that isn't the JSON shape Tavily documents. Retrying
            # gets the same body back.
            return ToolFailure(
                "the web search service sent back something unreadable.", retryable=False
            )

    async def search(self, query: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TAVILY_API_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": 3,
                    "include_answer": True,
                },
            )
            response.raise_for_status()
            data = response.json()
        return _format_results(data)


def _status_failure(status_code: int) -> ToolFailure:
    """Turns a rejected request into a line HUGO can say.

    Deliberately vague about *which* rejection: the status code, the URL,
    and the exception class are all facts about the transport, and this
    string is going to be paraphrased aloud.
    """
    if status_code in (401, 403):
        return ToolFailure(
            "web search isn't available — its credentials were refused.", retryable=False
        )
    if status_code >= 500 or status_code in _RETRYABLE_STATUS_CODES:
        return ToolFailure("the web search service is having trouble.", retryable=True)
    return ToolFailure("the web search service turned that request down.", retryable=False)


def _format_results(data: dict[str, Any]) -> str:
    parts: list[str] = []
    if answer := data.get("answer"):
        parts.append(answer)
    for result in data.get("results", []):
        parts.append(f"{result['title']}: {result['content']} ({result['url']})")
    return "\n".join(parts) if parts else "No results found."
