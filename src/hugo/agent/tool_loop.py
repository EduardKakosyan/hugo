"""Conversation loop implementing VoiceLoop's streaming Thinker protocol.

VEN-56 changed think() from blocking (full answer string, ~40s of dead air
measured live on dgx1) to an async generator of utterances — sentences
ready to speak, in speaking order. Reply text is sentence-split as LLM
deltas arrive, so the first sentence reaches TTS while the model is still
generating the rest.

Tool turns are never silent: whatever content the model produced before a
tool call has already been yielded (that's the acknowledgment — CONTEXT.md);
if it called a tool with no preamble at all, a canned acknowledgment is
yielded instead. The "still working" nudge for long tool turns lives in the
voice loop (gap-based, so it also covers a slow LLM pass), not here — a
generator can't emit on a timer while it's blocked inside a tool await.

Errors degrade to a spoken apology rather than propagating: the Thinker is
the system boundary isolating the voice loop from network/model/parsing
failures (the original incident: a real 400 from vLLM silently killed the
voice loop's task).
"""

import json
import logging
import re
from collections.abc import AsyncIterator

import httpx
from openai.types.chat import ChatCompletionMessageParam

from hugo.agent.llm_client import AssistantTurn, LlmClient, ToolCallRequest
from hugo.agent.web_search import WEB_SEARCH_TOOL_SCHEMA, WebSearchTool

logger = logging.getLogger(__name__)

# Concrete speech rules, not just "be conversational": tried live on dgx1
# 2026-07-22 with the one-liner version and Nemotron still produced
# written-register answers (long, structured, markdown-inflected) that
# sound absurd through TTS. Spell out what spoken text means.
DEFAULT_SYSTEM_PROMPT = (
    "You are HUGO, a voice assistant embodied in a small desk robot. "
    "Your name is HUGO and only HUGO. The spoken wake phrase that gets "
    "your attention may use a different name (currently 'hey Jarvis') "
    "and may appear inside the transcribed user message — treat it as a "
    "doorbell, not your name: never call yourself Jarvis or adopt any "
    "other persona. "
    "Everything you say is spoken aloud through text-to-speech, so reply "
    "exactly as a person talking: plain sentences with contractions, no "
    "markdown, no bullet points, no headers, no emojis, and never read "
    "out symbols or URLs. Lead with the answer in your first sentence. "
    "Keep replies to one to three short sentences unless the user "
    "explicitly asks for more detail. Before you call a tool, say one "
    "short sentence telling the user what you're about to do. When you "
    "use web search, weave what you found into a natural spoken answer "
    "and name the source briefly rather than citing links. If you don't "
    "know something or a search comes up empty, say so plainly."
)

_MAX_TOOL_ITERATIONS = 4

_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
_MARKDOWN_TOKENS = re.compile(r"[*_#`]+")

# Rotated through when the model calls a tool without saying anything first,
# so slow work is never silent (VEN-56: acknowledge + updates).
ACKNOWLEDGMENTS = (
    "Let me look that up.",
    "One moment, checking that now.",
    "Let me check on that.",
)


def speechify(text: str) -> str:
    """Best-effort scrub of written-text artifacts before TTS.

    The system prompt forbids markdown, but the model still slips —
    and through a speech synthesizer '**' and '- ' are read aloud or
    garbled. Belt-and-suspenders, not a substitute for the prompt.
    """
    text = _BULLET_PREFIX.sub("", text)
    text = _MARKDOWN_TOKENS.sub("", text)
    return re.sub(r"\s*\n+\s*", " ", text).strip()


class SentenceStream:
    """Buffers streamed text deltas and emits complete sentences.

    Splits at sentence-ish punctuation or newlines — the same boundaries
    the TTS server uses — so each emitted piece is a natural unit to hand
    to synthesis. Text still pending when the stream ends comes out of
    flush() (unpunctuated answers pass through whole; no worse than
    before).
    """

    _BOUNDARY = re.compile(r"(?<=[.!?;:])\s+|\n+")

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, delta: str) -> list[str]:
        self._pending += delta
        parts = self._BOUNDARY.split(self._pending)
        self._pending = parts.pop()
        return [part.strip() for part in parts if part.strip()]

    def flush(self) -> str:
        pending, self._pending = self._pending.strip(), ""
        return pending


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
        self._acknowledgment_count = 0

    async def think(self, user_text: str) -> AsyncIterator[str]:
        """Yields utterances to speak, in order, while the turn runs."""
        self._history.append({"role": "user", "content": user_text})
        try:
            async for utterance in self._respond():
                yield utterance
        except Exception:
            logger.exception("thinker failed mid-response")
            yield "Sorry, I ran into a problem thinking about that."

    async def _respond(self) -> AsyncIterator[str]:
        for _ in range(_MAX_TOOL_ITERATIONS):
            sentences = SentenceStream()
            turn: AssistantTurn | None = None
            spoke_any = False
            async for item in self._llm.stream_with_tools(
                self._history, tools=[WEB_SEARCH_TOOL_SCHEMA]
            ):
                if isinstance(item, AssistantTurn):
                    turn = item
                    continue
                for sentence in sentences.feed(item):
                    if spoken := speechify(sentence):
                        spoke_any = True
                        yield spoken
            assert turn is not None, "stream_with_tools must end with an AssistantTurn"
            self._history.append(turn.as_message_param())

            if remainder := speechify(sentences.flush()):
                spoke_any = True
                yield remainder

            if not turn.tool_calls:
                return

            if not spoke_any:
                yield self._next_acknowledgment()
            for call in turn.tool_calls:
                result = await self._dispatch(call)
                self._history.append({"role": "tool", "tool_call_id": call.id, "content": result})

        logger.warning("hit _MAX_TOOL_ITERATIONS without a final answer")
        yield "Sorry, I'm having trouble completing that search right now."

    def _next_acknowledgment(self) -> str:
        acknowledgment = ACKNOWLEDGMENTS[self._acknowledgment_count % len(ACKNOWLEDGMENTS)]
        self._acknowledgment_count += 1
        return acknowledgment

    async def _dispatch(self, call: ToolCallRequest) -> str:
        if call.name != "web_search":
            return f"unknown tool: {call.name}"
        try:
            query = json.loads(call.arguments)["query"]
            return await self._web_search.search(query)
        except (json.JSONDecodeError, KeyError) as exc:
            return f"invalid web search arguments: {exc}"
        except httpx.HTTPError as exc:
            return f"web search failed: {exc}"
