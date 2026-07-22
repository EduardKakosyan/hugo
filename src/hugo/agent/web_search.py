"""v1's only LLM tool (see memory/ADRs: tool scope is web search only for
v1). Backed by Tavily's REST API (https://tavily.com) -- chosen for its
free tier and JSON responses shaped for LLM tool results, not raw
HTML/SERP data. No SDK dependency: a single POST is simple enough to do
directly with httpx, which is already a core dependency.
"""

from typing import Any

import httpx
from openai.types.chat import ChatCompletionToolParam

TAVILY_API_URL = "https://api.tavily.com/search"

WEB_SEARCH_TOOL_SCHEMA: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information, facts, or anything not in "
            "your training data -- recent events, real-time data, or anything "
            "you're not confident about."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, as concise natural-language or keywords.",
                }
            },
            "required": ["query"],
        },
    },
}


class WebSearchTool:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

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


def _format_results(data: dict[str, Any]) -> str:
    parts: list[str] = []
    if answer := data.get("answer"):
        parts.append(answer)
    for result in data.get("results", []):
        parts.append(f"{result['title']}: {result['content']} ({result['url']})")
    return "\n".join(parts) if parts else "No results found."
