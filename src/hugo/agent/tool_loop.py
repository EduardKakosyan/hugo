"""Conversation loop implementing VoiceLoop's Thinker protocol.

Milestone 2: adds the first (and, per v1 scope, only) tool -- web search.
Each turn calls the LLM with tools available; if it returns tool_calls
instead of a final answer, this dispatches them and loops back with the
tool results appended, bounded by _MAX_TOOL_ITERATIONS so a model that
keeps calling tools can't hang a turn forever. The conversation history
management and the Thinker-protocol shape haven't changed from Milestone 1.
"""

import json
import logging

import httpx
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionMessageToolCallUnion

from hugo.agent.llm_client import LlmClient
from hugo.agent.web_search import WEB_SEARCH_TOOL_SCHEMA, WebSearchTool

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are HUGO, a helpful voice assistant. Keep responses concise and "
    "conversational, since they will be spoken aloud."
)

_MAX_TOOL_ITERATIONS = 4


class ToolLoop:
    def __init__(
        self,
        llm: LlmClient,
        web_search: WebSearchTool,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._llm = llm
        self._web_search = web_search
        self._history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt}
        ]

    async def think(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})

        for _ in range(_MAX_TOOL_ITERATIONS):
            message = await self._llm.complete_with_tools(
                self._history, tools=[WEB_SEARCH_TOOL_SCHEMA]
            )
            self._history.append(message.model_dump(exclude_none=True))  # type: ignore[arg-type]

            if not message.tool_calls:
                return message.content or ""

            for tool_call in message.tool_calls:
                result = await self._dispatch(tool_call)
                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        logger.warning("hit _MAX_TOOL_ITERATIONS without a final answer")
        return "Sorry, I'm having trouble completing that search right now."

    async def _dispatch(self, tool_call: ChatCompletionMessageToolCallUnion) -> str:
        if tool_call.type != "function":
            return f"unsupported tool call type: {tool_call.type}"
        if tool_call.function.name != "web_search":
            return f"unknown tool: {tool_call.function.name}"
        try:
            query = json.loads(tool_call.function.arguments)["query"]
            return await self._web_search.search(query)
        except httpx.HTTPError as exc:
            return f"web search failed: {exc}"
