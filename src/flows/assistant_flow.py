"""Main assistant flow — orchestrates voice → route → agent → response."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from crewai.flow.flow import Flow, listen, start  # type: ignore[import-untyped]

from src.crews.assistant_crew import AssistantCrew
from src.models.schemas import Emotion, IntentResult
from src.robot.controller import ReachyController
from src.router.intent_router import IntentRouter
from src.tools import robot_tools, vision_tools
from src.voice.pipeline import VoiceConfig, VoicePipeline

logger = logging.getLogger(__name__)


@dataclass
class FlowState:
    """Shared state across flow steps."""

    transcription: str = ""
    intent: IntentResult | None = None
    agent_output: str = ""
    is_running: bool = True


class AssistantFlow(Flow[FlowState]):  # type: ignore[misc]
    """HUGO's main interaction loop.

    Flow:
        initialize → idle_loop → (voice detected) → transcribe →
        route → execute → respond → idle_loop
    """

    def __init__(
        self,
        *,
        sim: bool = False,
        voice_enabled: bool = True,
        robot_host: str = "localhost",
        robot_port: int = 50051,
    ) -> None:
        super().__init__()
        self._sim = sim
        self._voice_enabled = voice_enabled

        # Components (initialized in start step)
        self._robot = ReachyController(host=robot_host, port=robot_port, sim=sim)
        self._voice = VoicePipeline(config=VoiceConfig())
        self._router = IntentRouter()
        self._crew = AssistantCrew()

    @start()  # type: ignore[misc]
    async def initialize(self) -> str:
        """Initialize all subsystems: robot, voice, router, models."""
        logger.info("Initializing HUGO assistant (sim=%s)...", self._sim)

        # Connect robot
        await self._robot.connect()

        # Set global controller references for tools
        robot_tools.set_controller(self._robot)
        vision_tools.set_controller(self._robot)

        # Initialize router
        await self._router.initialize()

        # Initialize voice pipeline
        if self._voice_enabled:
            await self._voice.initialize()

        # Greeting
        await self._robot.express(Emotion.HAPPY)
        greeting = "Hello! I'm Hugo, your personal assistant. How can I help?"

        if self._voice_enabled:
            await self._voice.speak(greeting)
        else:
            logger.info("HUGO: %s", greeting)

        logger.info("HUGO initialized and ready")
        return "initialized"

    @listen("initialized")  # type: ignore[misc]
    async def idle_loop(self, _: Any = None) -> str:
        """Wait for voice input or text input."""
        logger.info("Entering idle loop — waiting for input...")

        if self._voice_enabled:
            # Voice mode — listen via microphone
            async for result in self._voice.listen():
                if result.text:
                    self.state.transcription = result.text
                    logger.info("Heard: %s", result.text)
                    return result.text
        else:
            # Text mode — read from stdin
            text = await asyncio.get_event_loop().run_in_executor(None, lambda: input("You: "))
            if text.strip().lower() in ("quit", "exit", "bye"):
                self.state.is_running = False
                return "shutdown"
            self.state.transcription = text.strip()
            return text.strip()

        return ""

    @listen("idle_loop")  # type: ignore[misc]
    async def route_intent(self, user_text: str) -> IntentResult | None:
        """Route the user's input to the correct agent."""
        if not user_text or user_text == "shutdown":
            return None

        await self._robot.express(Emotion.THINKING)

        intent = self._router.route(user_text)
        self.state.intent = intent

        logger.info(
            "Routed to %s (confidence=%.2f, fallback=%s)",
            intent.category.value,
            intent.confidence,
            intent.fallback_used,
        )
        return intent

    @listen("route_intent")  # type: ignore[misc]
    async def execute_agent(self, intent: IntentResult | None) -> str:
        """Execute the appropriate CrewAI agent for the intent."""
        if intent is None:
            return ""

        user_input = self.state.transcription
        logger.info("Executing %s agent for: %s", intent.category.value, user_input)

        try:
            result = self._crew.kickoff_for_intent(intent.category, user_input)
            output = str(result)
            self.state.agent_output = output
            return output
        except Exception:
            logger.exception("Agent execution failed")
            error_msg = "I'm sorry, I had trouble processing that. Could you try again?"
            self.state.agent_output = error_msg
            return error_msg

    @listen("execute_agent")  # type: ignore[misc]
    async def respond(self, agent_output: str) -> str:
        """Deliver the response via TTS and robot expression."""
        if not agent_output:
            return "idle"

        # Parse emotion from output if possible
        await self._robot.express(Emotion.HAPPY)

        if self._voice_enabled:
            await self._voice.speak(agent_output)
        else:
            print(f"HUGO: {agent_output}")

        # Return to idle
        if self.state.is_running:
            # Re-enter idle loop
            return await self.idle_loop()

        return "shutdown"

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down HUGO...")

        if self._voice_enabled:
            farewell = "Goodbye! Have a great day."
            await self._voice.speak(farewell)

        await self._robot.express(Emotion.HAPPY)
        await self._robot.disconnect()
        logger.info("HUGO shutdown complete")
