"""Conversation loop implementing VoiceLoop's Thinker protocol.

Pass-through for now — no tools (Milestone 2 adds the first one: web
search). Shaped so that milestone is additive rather than a rewrite: adding
tool support means extending LlmClient to pass `tools=[...]` and expose
tool_calls on the response, and adding a dispatch-and-continue loop here
around the single `complete()` call below — the conversation history
management and the Thinker-protocol shape don't need to change.
"""

from openai.types.chat import ChatCompletionMessageParam

from hugo.agent.llm_client import LlmClient

DEFAULT_SYSTEM_PROMPT = (
    "You are HUGO, a helpful voice assistant. Keep responses concise and "
    "conversational, since they will be spoken aloud."
)


class ToolLoop:
    def __init__(self, llm: LlmClient, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self._llm = llm
        self._history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt}
        ]

    async def think(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        response_text = await self._llm.complete(self._history)
        self._history.append({"role": "assistant", "content": response_text})
        return response_text
