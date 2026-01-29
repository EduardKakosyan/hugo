"""Tests for the agent orchestrator and LLM providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agent.providers import PROVIDER_PRESETS, LLMProvider


class TestLLMProvider:
    def test_default_model(self) -> None:
        provider = LLMProvider()
        assert provider.model == "gemini/gemini-2.5-flash"

    def test_set_model_with_preset(self) -> None:
        provider = LLMProvider()
        provider.set_model("openai")
        assert provider.model == "openai/gpt-4o"

    def test_set_model_with_full_string(self) -> None:
        provider = LLMProvider()
        provider.set_model("ollama/codellama")
        assert provider.model == "ollama/codellama"

    def test_all_presets_defined(self) -> None:
        expected = {"gemini", "openai", "anthropic", "huggingface", "ollama"}
        assert set(PROVIDER_PRESETS.keys()) == expected

    @pytest.mark.asyncio
    async def test_chat_calls_litellm(self) -> None:
        provider = LLMProvider()
        mock_response = AsyncMock()
        mock_response.model_dump.return_value = {
            "choices": [{"message": {"content": "Hello!"}}]
        }

        with patch("src.agent.providers.litellm.acompletion", return_value=mock_response):
            result = await provider.chat([{"role": "user", "content": "Hi"}])
            assert result["choices"][0]["message"]["content"] == "Hello!"
