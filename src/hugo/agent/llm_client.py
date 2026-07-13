"""OpenAI-compatible streaming client against the local vLLM server
(ADR 0004: Nemotron-3-super-120b-a12b). vLLM's server doesn't check the API
key, but the openai SDK requires some value — a placeholder is fine.

NOT YET verified against a real served model: loading Nemotron-3 on vLLM
is a heavy (~60-70GB), long-running operation on the *shared* dgx1 box
(ADR 0002) — unlike the smaller checks elsewhere in this codebase, this
needs explicit coordination before running for real, not just a quick
spike. Built and tested here against the `openai` SDK's stable, documented
client interface instead.
"""

from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

DEFAULT_API_KEY = "not-needed"


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
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def complete(self, messages: list[ChatCompletionMessageParam]) -> str:
        """Collects a full streamed response into one string."""
        return "".join([delta async for delta in self.stream(messages)])
