"""Conversation loop implementing VoiceLoop's streaming Thinker protocol.

VEN-56 changed think() from blocking (full answer string, ~40s of dead air
measured live on dgx1) to an async generator of utterances — sentences
ready to speak, in speaking order. Reply text is sentence-split as LLM
deltas arrive, so the first sentence reaches TTS while the model is still
generating the rest.

Tool turns are never silent, but they aren't narrated either: the
acknowledgment races the tool. Each call runs as a task, the loop waits
`acknowledge_after_s` on it, and the canned phrase is yielded only if the
tool is still running — so a tool that returns in microseconds draws
nothing and only genuinely slow work gets announced. Whatever the model
said before the call counts as the acknowledgment (CONTEXT.md), and a turn
gets at most one however many tools it takes: a chain of tools is still one
question from the user's side. The "still working" nudge for the long tail
lives in the voice loop (gap-based, so it also covers a slow LLM pass), not
here — a generator can't emit on a timer while it's blocked inside a tool
await.

A failure a tool marks `retryable` (ToolFailure.retryable) gets up to
`_MAX_TOOL_ATTEMPTS` attempts, with a spoken line between them — the same
generator that races the filler owns the retry, because narrating an
attempt has to be a `yield` and only the turn loop can yield. Retries are
per call, never per batch: a turn that remembers a fact and searches the
web must not re-run the successful write because the search timed out.

Errors degrade to a spoken apology rather than propagating: the Thinker is
the system boundary isolating the voice loop from network/model/parsing
failures (the original incident: a real 400 from vLLM silently killed the
voice loop's task).

Barge-in can also cancel a turn mid-tool, leaving history holding an
assistant `tool_calls` message with no reply — nothing downstream rejects
that (vLLM never cross-references `tool_call_id`), but the next turn's
history needs it healed anyway, so `think()` repairs the tail before
appending the next user message (research §3).
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, cast

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from hugo.agent.llm_client import AssistantTurn, LlmClient, ToolCallRequest
from hugo.agent.tools import Tool, ToolFailure

logger = logging.getLogger(__name__)

# Concrete speech rules, not just "be conversational": tried live on dgx1
# 2026-07-22 with the one-liner version and Nemotron still produced
# written-register answers (long, structured, markdown-inflected) that
# sound absurd through TTS. Spell out what spoken text means.
DEFAULT_SYSTEM_PROMPT = (
    "You are HUGO, a voice assistant embodied in a small desk robot. "
    "Your name is HUGO and only HUGO. The spoken wake phrase ('hey Hugo') "
    "may appear inside the transcribed user message — treat it as a "
    "doorbell, not part of what's being asked, and never adopt any other "
    "persona regardless of what the transcript calls you. "
    "Everything you say is spoken aloud through text-to-speech, so reply "
    "exactly as a person talking: plain sentences with contractions, no "
    "markdown, no bullet points, no headers, no emojis, and never read "
    "out symbols or URLs. Lead with the answer in your first sentence. "
    "Keep replies to one to three short sentences unless the user "
    "explicitly asks for more detail. Don't announce that you're about "
    "to use a tool — use it and answer. When a tool gives you results, "
    "weave them into a natural spoken answer and name the source "
    "briefly rather than citing links. If you don't know something, or "
    "a tool comes up empty or fails, say so plainly. "
    # Phrased as an incapacity, not an instruction, because that is the
    # form that works here. Live on dgx1 2026-08-11, the polite version
    # ("save it with remember_fact without being asked") had Nemotron
    # answer "I'll remember that your standup is at 9:30" while calling
    # nothing and storing nothing — a promise it can't keep, which is
    # worse than refusing. The get_current_time rule below never had that
    # problem, and the only thing it does differently is deny the model
    # the capability outright before naming the tool.
    "You have no memory of your own. Nothing you hear is retained unless "
    "you write it down, so saying you'll remember something without "
    "calling remember_fact is a promise you can't keep. When the user "
    "tells you something durable about themselves — a standing meeting "
    "time, a preference, a name, a deadline — call remember_fact, then "
    "say what you saved as part of your reply. Let passing chatter go. "
    "A correction is a new fact, not an edit. You begin every "
    "conversation knowing nothing they have ever told you: call "
    "recall_facts before answering anything that depends on something "
    "they said earlier — what they planned, prefer, or asked you to "
    "keep track of — rather than saying you have no record of it. "
    "You have no idea what day or time it is unless you ask: call "
    "get_current_time before answering anything that depends on today, "
    "tomorrow, this week, or how long ago something was. "
    "Start every reply with exactly one mood tag in square brackets — "
    "[neutral], [cheerful], [thoughtful], [apologetic], [excited], or "
    "[curious] — matching what you're about to say; it drives your body "
    "language. The tag is removed before your words are spoken: never "
    "mention it or read it aloud."
)

# Spoken-mood vocabulary the model tags each reply with (VEN-57): the main
# LLM is the "model that thinks about movement" — it already knows what
# it's about to say, so a tag costs a few tokens where a separate model
# would burn shared-box memory to guess at the same information.
MOODS = ("neutral", "cheerful", "thoughtful", "apologetic", "excited", "curious")
_MOOD_TAG = re.compile(r"\[(" + "|".join(MOODS) + r")\]\s*", re.IGNORECASE)

_MAX_TOOL_ITERATIONS = 4

# Attempts at ONE call, not passes through the LLM (_MAX_TOOL_ITERATIONS
# above) — a different budget for a different thing. The two multiply in
# the worst case (12 invocations), which is acceptable because only a
# failure the tool marks retryable consumes an attempt, and in-tool retries
# are cheap where the LLM pass is the expensive resource.
_MAX_TOOL_ATTEMPTS = 3

_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
_MARKDOWN_TOKENS = re.compile(r"[*_#`]+")

# Rotated through when a tool is still running after acknowledge_after_s and
# the model said nothing first, so slow work is never silent (VEN-56:
# acknowledge + updates). Deliberately tool-NEUTRAL: "let me look that up"
# was written when the only tool was a web search, and it's wrong for
# remembering a fact — as it will be for most of what MCP brings.
ACKNOWLEDGMENTS = (
    "One moment, checking that now.",
    "Just a second.",
    "Give me a moment on that.",
)

# Spoken once BETWEEN attempts of the same call, and only when another
# attempt is actually coming next — not after the last one, which goes
# straight to the failure text a model can act on (a different tool, or
# different arguments, within its own _MAX_TOOL_ITERATIONS budget).
RETRY_NOTICE = "That didn't go through, let me try again."

# The _MAX_TOOL_ITERATIONS pass budget ran out without a final answer.
# Tool-neutral on purpose: this line used to say "completing that search"
# from when web search was the only tool HUGO had — wrong for three of
# the four tools in the set now, and for whatever MCP adds next round.
EXHAUSTED_FALLBACK = "Sorry, I'm having trouble completing that right now."


def _field(message: ChatCompletionMessageParam, key: str) -> Any:
    """Reads one key off a history entry regardless of which of the six
    `ChatCompletionMessageParam` roles it turns out to be.

    Only assistant messages carry `tool_calls`; only tool messages carry
    `tool_call_id`. mypy checks a Union of TypedDicts key-by-key, so asking
    for either on the wrong role is a static error even though these are
    plain dicts at runtime — the same escape hatch `as_message_param`
    already uses when it builds one.
    """
    return cast(dict[str, Any], message).get(key)


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
    """The turn loop. It knows how many tools there are and nothing else
    about them: the collection supplies the schemas it offers the model and
    the map it dispatches through, both keyed off the schemas themselves,
    so adding a capability never touches this file (docs/adr/0006)."""

    def __init__(
        self,
        llm: LlmClient,
        tools: Sequence[Tool],
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        on_mood: Callable[[str], None] | None = None,
        acknowledge_after_s: float = 1.0,
    ) -> None:
        self._llm = llm
        self._schemas: list[ChatCompletionToolParam] = [tool.schema for tool in tools]
        self._by_name: dict[str, Tool] = {tool.schema["function"]["name"]: tool for tool in tools}
        self._on_mood = on_mood
        self._acknowledge_after_s = acknowledge_after_s
        self._history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt}
        ]
        self._acknowledgment_count = 0

    def _strip_mood(self, text: str) -> str:
        """Removes mood tags from an outgoing utterance, reporting the
        first to on_mood. Runs on EVERY spoken path: a tag must never
        reach TTS — same discipline as reasoning traces (CONTEXT.md)."""
        tags = _MOOD_TAG.findall(text)
        if not tags:
            return text
        if self._on_mood is not None:
            try:
                self._on_mood(tags[0].lower())
            except Exception:
                logger.exception("mood callback failed; continuing")
        return _MOOD_TAG.sub("", text)

    async def think(self, user_text: str) -> AsyncIterator[str]:
        """Yields utterances to speak, in order, while the turn runs."""
        self._repair_orphaned_tool_calls()
        self._history.append({"role": "user", "content": user_text})
        try:
            async for utterance in self._respond():
                yield utterance
        except Exception:
            logger.exception("thinker failed mid-response")
            yield "Sorry, I ran into a problem thinking about that."

    def _repair_orphaned_tool_calls(self) -> None:
        """Heals a turn barge-in cut short inside a tool `await`.

        Cancellation lands wherever the generator happens to be, which can
        be mid-dispatch: the assistant's `tool_calls` message is already in
        history, but the call running when the cancellation hit — and every
        call after it — never got its `role: tool` reply appended. Nothing
        downstream rejects that: the chat template renders the tool_calls
        branch unconditionally and vLLM never cross-references
        `tool_call_id` against the replies that follow (research §3), so a
        ragged history is silently tolerated right up until it confuses the
        model on the next pass.

        Runs at the top of every think(), before a cancellation handler
        could exist for it, so it heals history left ragged by any cause —
        not just barge-in — on a plain synchronous path.
        """
        history = self._history
        last_assistant = next(
            (
                i
                for i in range(len(history) - 1, -1, -1)
                if _field(history[i], "role") == "assistant"
            ),
            None,
        )
        if last_assistant is None:
            return
        tool_calls = _field(history[last_assistant], "tool_calls")
        if not tool_calls:
            return
        answered = {
            _field(message, "tool_call_id")
            for message in history[last_assistant + 1 :]
            if _field(message, "role") == "tool"
        }
        for call in tool_calls:
            if call["id"] in answered:
                continue
            # A statement of fact, not a failure report: the tool may well
            # have succeeded (a fact written, a search returned) — telling
            # the model it *failed* would have HUGO apologising over a
            # write that actually landed.
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": "interrupted by the user before this finished",
                }
            )

    async def _respond(self) -> AsyncIterator[str]:
        # Per turn, not per pass: a chain of tools (the date, then the
        # notes) is one question from the user's side, so it gets one
        # acknowledgment rather than a hop-by-hop narration. A genuinely
        # long chain is the voice loop's 8s nudge to cover.
        acknowledged = False
        for _ in range(_MAX_TOOL_ITERATIONS):
            sentences = SentenceStream()
            turn: AssistantTurn | None = None
            spoke_any = False
            async for item in self._llm.stream_with_tools(self._history, tools=self._schemas):
                if isinstance(item, AssistantTurn):
                    turn = item
                    continue
                for sentence in sentences.feed(item):
                    if spoken := speechify(self._strip_mood(sentence)):
                        spoke_any = True
                        yield spoken
            assert turn is not None, "stream_with_tools must end with an AssistantTurn"
            self._history.append(turn.as_message_param())

            if remainder := speechify(self._strip_mood(sentences.flush())):
                spoke_any = True
                yield remainder

            if not turn.tool_calls:
                return

            # Anything the model said ahead of the call IS the
            # acknowledgment, so it suppresses the canned one.
            acknowledged = acknowledged or spoke_any
            for call in turn.tool_calls:
                result: str | ToolFailure = ""
                # Attempts happen per CALL, never per batch: a turn that
                # remembers a fact and searches the web must not re-run the
                # successful write because the search timed out.
                for attempt in range(_MAX_TOOL_ATTEMPTS):
                    task = asyncio.create_task(self._invoke(call))
                    try:
                        # Race the tool rather than predicting its latency: the
                        # phrase is only worth saying if the wait is real, and
                        # no per-tool "is this slow?" metadata could know that
                        # for an MCP tool nobody has timed.
                        await asyncio.wait([task], timeout=self._acknowledge_after_s)
                        if not task.done() and not acknowledged:
                            acknowledged = True
                            yield self._next_acknowledgment()
                        result = await task
                    finally:
                        # Barge-in cancels this generator wherever it happens to
                        # be, which can be either await above; carry the
                        # cancellation into the tool the way a plain `await`
                        # used to, rather than orphaning a task nobody collects.
                        # A no-op once the task is done.
                        task.cancel()
                    if not (isinstance(result, ToolFailure) and result.retryable):
                        break
                    # Only narrate if another attempt is actually coming —
                    # the last attempt's failure goes straight to history
                    # for the model to read and act on instead.
                    if attempt + 1 < _MAX_TOOL_ATTEMPTS:
                        yield RETRY_NOTICE
                content = result.text if isinstance(result, ToolFailure) else result
                self._history.append({"role": "tool", "tool_call_id": call.id, "content": content})

        logger.warning("hit _MAX_TOOL_ITERATIONS without a final answer")
        yield EXHAUSTED_FALLBACK

    def _next_acknowledgment(self) -> str:
        acknowledgment = ACKNOWLEDGMENTS[self._acknowledgment_count % len(ACKNOWLEDGMENTS)]
        self._acknowledgment_count += 1
        return acknowledgment

    async def _invoke(self, call: ToolCallRequest) -> str | ToolFailure:
        """Resolves a call through the schema-derived map and runs it.

        These two are the loop's own failures — the only ones it can
        recognise without knowing what any tool does — and neither can go
        differently on a second attempt. Everything past here is the tool's
        to classify (agent/tools/__init__.py)."""
        tool = self._by_name.get(call.name)
        if tool is None:
            return ToolFailure(f"there's no tool called {call.name}.", retryable=False)
        try:
            # A no-argument tool can arrive with an empty arguments string
            # rather than "{}"; that's an empty call, not a broken one.
            arguments = json.loads(call.arguments) if call.arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = None
        if not isinstance(arguments, dict):
            return ToolFailure(
                f"the arguments for {call.name} weren't valid JSON.", retryable=False
            )
        return await tool.invoke(arguments)
