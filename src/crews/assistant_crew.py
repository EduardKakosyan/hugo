"""CrewAI crew wiring — agents + tasks + MCP tools."""

from __future__ import annotations

import os
from typing import Any

from crewai import Agent, Crew, Process, Task  # type: ignore[import-untyped]
from crewai.project import CrewBase, agent, crew, task  # type: ignore[import-untyped]

from src.models.schemas import IntentCategory
from src.tools.robot_tools import ExpressTool, LookAtTool, SpeakTool
from src.tools.vision_tools import CaptureFrameTool, DescribeSceneTool

# ── LLM Configuration ─────────────────────────────────────────────────────────
# CrewAI supports litellm-style model strings.
# Local MLX models served via mlx_lm.server are OpenAI-compatible on localhost.

LOCAL_LLM = os.getenv("HUGO_LOCAL_LLM", "openai/qwen3-32b")
CLOUD_LLM = os.getenv("HUGO_CLOUD_LLM", "gemini/gemini-2.5-flash")
VISION_LLM = os.getenv("HUGO_VISION_LLM", "openai/qwen3-vl-4b")

# MCP server commands for CrewAI agent integration
MS_GRAPH_MCP = "python -m src.mcp_servers.ms_graph"
LINEAR_MCP = "python -m src.mcp_servers.linear_server"
FIREFLIES_MCP = "python -m src.mcp_servers.fireflies"


@CrewBase  # type: ignore[misc]
class AssistantCrew:
    """HUGO's main crew — routes to specialist agents via MCP tools."""

    agents_config = "src/config/agents.yaml"
    tasks_config = "src/config/tasks.yaml"

    # ── Agents ─────────────────────────────────────────────────────────────

    @agent  # type: ignore[misc]
    def orchestrator(self) -> Agent:
        return Agent(
            config=self.agents_config["orchestrator"],  # type: ignore[index]
            llm=LOCAL_LLM,
            tools=[SpeakTool(), ExpressTool(), LookAtTool()],
            verbose=True,
        )

    @agent  # type: ignore[misc]
    def email_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["email_agent"],  # type: ignore[index]
            llm=LOCAL_LLM,
            mcps=[{"type": "stdio", "command": MS_GRAPH_MCP}],
            verbose=True,
        )

    @agent  # type: ignore[misc]
    def calendar_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["calendar_agent"],  # type: ignore[index]
            llm=LOCAL_LLM,
            mcps=[{"type": "stdio", "command": MS_GRAPH_MCP}],
            verbose=True,
        )

    @agent  # type: ignore[misc]
    def linear_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["linear_agent"],  # type: ignore[index]
            llm=LOCAL_LLM,
            mcps=[{"type": "stdio", "command": LINEAR_MCP}],
            verbose=True,
        )

    @agent  # type: ignore[misc]
    def fireflies_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["fireflies_agent"],  # type: ignore[index]
            llm=LOCAL_LLM,
            mcps=[{"type": "stdio", "command": FIREFLIES_MCP}],
            verbose=True,
        )

    @agent  # type: ignore[misc]
    def vision_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["vision_agent"],  # type: ignore[index]
            llm=VISION_LLM,
            tools=[CaptureFrameTool(), DescribeSceneTool()],
            verbose=True,
        )

    @agent  # type: ignore[misc]
    def general_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["general_agent"],  # type: ignore[index]
            llm=LOCAL_LLM,
            tools=[SpeakTool(), ExpressTool()],
            verbose=True,
        )

    # ── Tasks ──────────────────────────────────────────────────────────────

    @task  # type: ignore[misc]
    def orchestrate_task(self) -> Task:
        return Task(config=self.tasks_config["orchestrate_task"])  # type: ignore[index]

    @task  # type: ignore[misc]
    def email_task(self) -> Task:
        return Task(config=self.tasks_config["email_task"])  # type: ignore[index]

    @task  # type: ignore[misc]
    def calendar_task(self) -> Task:
        return Task(config=self.tasks_config["calendar_task"])  # type: ignore[index]

    @task  # type: ignore[misc]
    def linear_task(self) -> Task:
        return Task(config=self.tasks_config["linear_task"])  # type: ignore[index]

    @task  # type: ignore[misc]
    def fireflies_task(self) -> Task:
        return Task(config=self.tasks_config["fireflies_task"])  # type: ignore[index]

    @task  # type: ignore[misc]
    def vision_task(self) -> Task:
        return Task(config=self.tasks_config["vision_task"])  # type: ignore[index]

    @task  # type: ignore[misc]
    def general_task(self) -> Task:
        return Task(config=self.tasks_config["general_task"])  # type: ignore[index]

    # ── Crew Factory ───────────────────────────────────────────────────────

    @crew  # type: ignore[misc]
    def crew(self) -> Crew:
        """Full crew with all agents — used by the orchestrator."""
        return Crew(
            agents=self.agents,  # type: ignore[attr-defined]
            tasks=self.tasks,  # type: ignore[attr-defined]
            process=Process.sequential,
            verbose=True,
        )

    def get_crew_for_intent(self, intent: IntentCategory) -> Crew:
        """Get a focused crew with only the agent needed for a given intent."""
        agent_map: dict[IntentCategory, tuple[Agent, Task]] = {
            IntentCategory.EMAIL: (self.email_agent(), self.email_task()),
            IntentCategory.CALENDAR: (self.calendar_agent(), self.calendar_task()),
            IntentCategory.LINEAR: (self.linear_agent(), self.linear_task()),
            IntentCategory.FIREFLIES: (self.fireflies_agent(), self.fireflies_task()),
            IntentCategory.VISION: (self.vision_agent(), self.vision_task()),
            IntentCategory.GENERAL_CHAT: (self.general_agent(), self.general_task()),
            IntentCategory.ROBOT_CONTROL: (self.general_agent(), self.general_task()),
        }

        selected_agent, selected_task = agent_map.get(
            intent, (self.general_agent(), self.general_task())
        )

        return Crew(
            agents=[selected_agent],
            tasks=[selected_task],
            process=Process.sequential,
            verbose=True,
        )

    def kickoff_for_intent(self, intent: IntentCategory, user_input: str) -> Any:
        """Kick off the appropriate crew for a given intent."""
        focused_crew = self.get_crew_for_intent(intent)
        return focused_crew.kickoff(inputs={"user_input": user_input})
