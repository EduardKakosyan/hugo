"""Tests for CrewAI crew configuration."""

from __future__ import annotations

from src.models.schemas import IntentCategory


class TestAssistantCrew:
    """Test crew configuration and intent routing."""

    def test_intent_categories_complete(self) -> None:
        """All intent categories are defined."""
        categories = list(IntentCategory)
        assert len(categories) == 7
        assert IntentCategory.EMAIL in categories
        assert IntentCategory.CALENDAR in categories
        assert IntentCategory.LINEAR in categories
        assert IntentCategory.FIREFLIES in categories
        assert IntentCategory.VISION in categories
        assert IntentCategory.GENERAL_CHAT in categories
        assert IntentCategory.ROBOT_CONTROL in categories

    def test_agents_yaml_exists(self) -> None:
        """Agents config file exists."""
        from pathlib import Path

        agents_path = Path("src/config/agents.yaml")
        assert agents_path.exists(), "agents.yaml not found"

    def test_tasks_yaml_exists(self) -> None:
        """Tasks config file exists."""
        from pathlib import Path

        tasks_path = Path("src/config/tasks.yaml")
        assert tasks_path.exists(), "tasks.yaml not found"

    def test_agents_yaml_has_all_agents(self) -> None:
        """All required agents are defined in YAML."""
        from pathlib import Path

        import yaml

        with Path("src/config/agents.yaml").open() as f:
            config = yaml.safe_load(f)

        required = [
            "orchestrator",
            "email_agent",
            "calendar_agent",
            "linear_agent",
            "fireflies_agent",
            "vision_agent",
            "general_agent",
        ]
        for agent_name in required:
            assert agent_name in config, f"Agent '{agent_name}' missing from agents.yaml"
            assert "role" in config[agent_name], f"Agent '{agent_name}' missing 'role'"
            assert "goal" in config[agent_name], f"Agent '{agent_name}' missing 'goal'"
            assert "backstory" in config[agent_name], f"Agent '{agent_name}' missing 'backstory'"

    def test_tasks_yaml_has_all_tasks(self) -> None:
        """All required tasks are defined in YAML."""
        from pathlib import Path

        import yaml

        with Path("src/config/tasks.yaml").open() as f:
            config = yaml.safe_load(f)

        required = [
            "orchestrate_task",
            "email_task",
            "calendar_task",
            "linear_task",
            "fireflies_task",
            "vision_task",
            "general_task",
        ]
        for task_name in required:
            assert task_name in config, f"Task '{task_name}' missing from tasks.yaml"
            assert "description" in config[task_name], f"Task '{task_name}' missing 'description'"
            assert "expected_output" in config[task_name], (
                f"Task '{task_name}' missing 'expected_output'"
            )
            assert "agent" in config[task_name], f"Task '{task_name}' missing 'agent'"
