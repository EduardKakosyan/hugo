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
import re

import httpx
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionMessageToolCallUnion

from hugo.agent.llm_client import LlmClient
from hugo.agent.web_search import WEB_SEARCH_TOOL_SCHEMA, WebSearchTool

logger = logging.getLogger(__name__)

# Concrete speech rules, not just "be conversational": tried live on dgx1
# 2026-07-22 with the one-liner version and Nemotron still produced
# written-register answers (long, structured, markdown-inflected) that
# sound absurd through TTS. Spell out what spoken text means.
DEFAULT_SYSTEM_PROMPT = (
    "You are HUGO, a voice assistant embodied in a small desk robot. "
    "Everything you say is spoken aloud through text-to-speech, so reply "
    "exactly as a person talking: plain sentences with contractions, no "
    "markdown, no bullet points, no headers, no emojis, and never read "
    "out symbols or URLs. Lead with the answer in your first sentence. "
    "Keep replies to one to three short sentences unless the user "
    "explicitly asks for more detail. When you use web search, weave "
    "what you found into a natural spoken answer and name the source "
    "briefly rather than citing links. If you don't know something or a "
    "search comes up empty, say so plainly."
)

_MAX_TOOL_ITERATIONS = 4

_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
_MARKDOWN_TOKENS = re.compile(r"[*_#`]+")


def speechify(text: str) -> str:
    """Best-effort scrub of written-text artifacts before TTS.

    The system prompt forbids markdown, but the model still slips —
    and through a speech synthesizer '**' and '- ' are read aloud or
    garbled. Belt-and-suspenders, not a substitute for the prompt.
    """
    text = _BULLET_PREFIX.sub("", text)
    text = _MARKDOWN_TOKENS.sub("", text)
    return re.sub(r"\s*\n+\s*", " ", text).strip()


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
                return speechify(message.content or "")

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
