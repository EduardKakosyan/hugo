"""Main agent orchestrator — ties together LLM, robot, integrations, and tools."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from src.agent.providers import LLMProvider
from src.agent.tools import BUILTIN_TOOLS
from src.config import AgentSettings
from src.integrations.registry import IntegrationRegistry
from src.robot.controller import RobotController

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates LLM reasoning, tool execution, and robot actions."""

    def __init__(
        self,
        config: AgentSettings,
        robot: RobotController,
        integrations: IntegrationRegistry,
    ) -> None:
        self._config = config
        self._robot = robot
        self._integrations = integrations
        self._llm = LLMProvider(config.default_provider)
        self._history: list[dict[str, Any]] = []

    @property
    def llm(self) -> LLMProvider:
        return self._llm

    def _build_messages(self, user_message: str) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": self._config.system_prompt}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _get_all_tools(self) -> list[dict[str, Any]]:
        tools = list(BUILTIN_TOOLS)
        for integration in self._integrations.active_integrations():
            tools.extend(integration.get_tools_sync())
        return tools

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool call and return the result as a string."""
        if name == "move_head":
            await self._robot.goto_target(
                roll=args.get("roll", 0.0),
                pitch=args.get("pitch", 0.0),
                yaw=args.get("yaw", 0.0),
                duration=args.get("duration", 1.0),
            )
            return "Head moved successfully."

        if name == "look_at_camera":
            await self._robot.goto_target(roll=0, pitch=0, yaw=0, duration=0.8)
            return "Looking at camera."

        if name == "wave":
            # Perform a simple wave sequence
            for yaw in [30, -30, 20, -20, 0]:
                await self._robot.goto_target(yaw=yaw, duration=0.3)
            return "Wave completed."

        if name == "analyze_scene":
            from src.vision.processor import VisionProcessor

            processor = VisionProcessor(self._llm)
            frame = await self._robot.get_frame()
            if frame is None:
                return "Camera not available."
            question = args.get("question", "Describe what you see.")
            result = await processor.analyze_frame(frame, question)
            return result

        # Try integration tools
        result = await self._integrations.execute_tool(name, args)
        if result is not None:
            return result

        return f"Unknown tool: {name}"

    async def chat(self, user_message: str) -> str:
        """Process a user message and return the agent's response."""
        messages = self._build_messages(user_message)
        tools = self._get_all_tools()

        response = await self._llm.chat(messages, tools=tools if tools else None)
        choice = response["choices"][0]
        message = choice["message"]

        # Handle tool calls
        if message.get("tool_calls"):
            messages.append(message)
            for tool_call in message["tool_calls"]:
                fn = tool_call["function"]
                raw_args = fn["arguments"]
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                result = await self._execute_tool(fn["name"], args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                })

            # Get final response after tool execution
            response = await self._llm.chat(messages)
            choice = response["choices"][0]
            message = choice["message"]

        content = message.get("content", "")

        # Update history
        self._history.append({"role": "user", "content": user_message})
        self._history.append({"role": "assistant", "content": content})

        # Keep history bounded
        if len(self._history) > 40:
            self._history = self._history[-30:]

        return content

    async def stream_chat(self, user_message: str) -> AsyncIterator[str]:
        """Stream a chat response token by token."""
        messages = self._build_messages(user_message)
        tools = self._get_all_tools()

        full_content = ""
        async for chunk in self._llm.stream_chat(messages, tools=tools if tools else None):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            token = delta.get("content", "")
            if token:
                full_content += token
                yield token

        self._history.append({"role": "user", "content": user_message})
        self._history.append({"role": "assistant", "content": full_content})

        if len(self._history) > 40:
            self._history = self._history[-30:]
