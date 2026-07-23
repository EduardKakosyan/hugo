"""OpenAI-compatible streaming client against the local vLLM server
(ADR 0004: Nemotron-3-super-120b-a12b). vLLM's server doesn't check the API
key, but the openai SDK requires some value — a placeholder is fine.

stream_with_tools is the voice path (VEN-56): it yields content-text deltas
the moment they arrive so the tool loop can start speaking sentences while
the model is still generating, then yields exactly one AssistantTurn with
the fully-assembled message (content + any tool calls). Tool-call fragments
are accumulated by stream index per the OpenAI streaming contract; with
vLLM's qwen3_coder parser the arguments arrive whole rather than
token-by-token, but the accumulation handles either. Reasoning deltas are
deliberately never yielded — the reasoning trace is separated server-side
by vLLM's nemotron_v3 parser (see orchestrator._build_specs) and must
never reach TTS (CONTEXT.md: Reasoning trace).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from openai import NOT_GIVEN, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

DEFAULT_API_KEY = "not-needed"

# Nemotron 3's model card recommends these "across all tasks and serving
# backends" — left implicit before VEN-56, which meant vLLM's own defaults.
TEMPERATURE = 1.0
TOP_P = 0.95


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AssistantTurn:
    """One assistant response, reassembled from its stream."""

    content: str
    tool_calls: tuple[ToolCallRequest, ...]

    def as_message_param(self) -> ChatCompletionMessageParam:
        message: dict[str, Any] = {"role": "assistant"}
        if self.content:
            message["content"] = self.content
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in self.tool_calls
            ]
        return cast(ChatCompletionMessageParam, message)


class LlmClient:
    def __init__(self, base_url: str, model: str, api_key: str = DEFAULT_API_KEY) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def stream(self, messages: list[ChatCompletionMessageParam]) -> AsyncIterator[str]:
        """Yields response text deltas as they arrive."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def complete(self, messages: list[ChatCompletionMessageParam]) -> str:
        """Collects a full streamed response into one string."""
        return "".join([delta async for delta in self.stream(messages)])

    async def stream_with_tools(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam],
    ) -> AsyncIterator[str | AssistantTurn]:
        """Yields content deltas as they arrive, then one final AssistantTurn."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            # vLLM 0.25 rejects `tools: []` with a real 400 ("must not be an
            # empty array") — found live on dgx1 2026-07-23. Omit the field
            # entirely when there are no tools.
            tools=tools or NOT_GIVEN,
            stream=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
        )
        content_parts: list[str] = []
        calls_by_index: dict[int, dict[str, str]] = {}
        async for chunk in response:
            if not chunk.choices:
                continue  # e.g. a final usage-only chunk
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                yield delta.content
            for fragment in delta.tool_calls or []:
                slot = calls_by_index.setdefault(
                    fragment.index, {"id": "", "name": "", "arguments": ""}
                )
                if fragment.id:
                    slot["id"] = fragment.id
                if fragment.function is not None:
                    if fragment.function.name:
                        slot["name"] = fragment.function.name
                    if fragment.function.arguments:
                        slot["arguments"] += fragment.function.arguments
        yield AssistantTurn(
            content="".join(content_parts),
            tool_calls=tuple(
                ToolCallRequest(id=slot["id"], name=slot["name"], arguments=slot["arguments"])
                for _index, slot in sorted(calls_by_index.items())
            ),
        )
