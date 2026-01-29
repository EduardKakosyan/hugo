"""Multi-provider LLM interface using LiteLLM."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import litellm

logger = logging.getLogger(__name__)

# Supported provider presets
PROVIDER_PRESETS: dict[str, str] = {
    "gemini": "gemini/gemini-2.5-flash",
    "openai": "openai/gpt-4o",
    "anthropic": "anthropic/claude-sonnet-4-20250514",
    "huggingface": "huggingface/mistralai/Ministral-3-14B-Reasoning-2512",
    "ollama": "ollama/llama3.1",
}


class LLMProvider:
    """Unified LLM interface that can switch between providers at runtime."""

    def __init__(self, default_model: str = "gemini/gemini-2.5-flash") -> None:
        self._model = default_model
        litellm.drop_params = True

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model: str) -> None:
        """Switch to a different model. Accepts full litellm model string or preset name."""
        if model in PROVIDER_PRESETS:
            self._model = PROVIDER_PRESETS[model]
        else:
            self._model = model
        logger.info("LLM provider switched to: %s", self._model)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Send a chat completion request."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await litellm.acompletion(**kwargs)
        return response.model_dump()

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a chat completion response."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            yield chunk.model_dump()

    async def vision_analysis(
        self,
        image_base64: str,
        prompt: str = "Describe what you see in this image.",
        model: str | None = None,
    ) -> str:
        """Analyze an image using a multimodal model."""
        target_model = model or self._model
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ]
        response = await litellm.acompletion(model=target_model, messages=messages)
        return response.choices[0].message.content or ""
