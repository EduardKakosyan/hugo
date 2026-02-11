"""Tests for robot and vision tools."""

from __future__ import annotations

import asyncio

import pytest

from src.models.schemas import Emotion
from src.robot.controller import ReachyController
from src.tools import robot_tools, vision_tools


class TestReachyController:
    """Test the Reachy Mini controller in simulation mode."""

    @pytest.fixture
    def controller(self) -> ReachyController:
        ctrl = ReachyController(sim=True)
        asyncio.get_event_loop().run_until_complete(ctrl.connect())
        return ctrl

    def test_sim_mode(self, controller: ReachyController) -> None:
        assert controller.is_sim is True
        assert controller.state.connected is True

    def test_speak(self, controller: ReachyController) -> None:
        asyncio.get_event_loop().run_until_complete(controller.speak("hello"))
        assert controller.state.is_speaking is False

    def test_look_at(self, controller: ReachyController) -> None:
        asyncio.get_event_loop().run_until_complete(controller.look_at(1.0, 0.5, 0.0))
        assert controller.state.head_position == (1.0, 0.5, 0.0)

    def test_express(self, controller: ReachyController) -> None:
        asyncio.get_event_loop().run_until_complete(controller.express(Emotion.HAPPY))
        assert controller.state.current_emotion == Emotion.HAPPY

    def test_capture_frame_sim_returns_none(self, controller: ReachyController) -> None:
        result = asyncio.get_event_loop().run_until_complete(controller.capture_frame())
        assert result is None

    def test_disconnect(self, controller: ReachyController) -> None:
        asyncio.get_event_loop().run_until_complete(controller.disconnect())
        assert controller.state.connected is False


class TestRobotTools:
    """Test CrewAI robot tools."""

    @pytest.fixture(autouse=True)
    def setup_controller(self) -> None:
        ctrl = ReachyController(sim=True)
        asyncio.get_event_loop().run_until_complete(ctrl.connect())
        robot_tools.set_controller(ctrl)

    def test_speak_tool(self) -> None:
        tool = robot_tools.SpeakTool()
        result = tool._run(text="test message")
        assert "Spoke" in result

    def test_express_tool(self) -> None:
        tool = robot_tools.ExpressTool()
        result = tool._run(emotion="happy")
        assert "happy" in result.lower()

    def test_look_at_tool(self) -> None:
        tool = robot_tools.LookAtTool()
        result = tool._run(x=1.0, y=0.0, z=0.0)
        assert "Looking" in result

    def test_rotate_tool(self) -> None:
        tool = robot_tools.RotateTool()
        result = tool._run(degrees=45.0)
        assert "45" in result


class TestVisionTools:
    """Test CrewAI vision tools."""

    @pytest.fixture(autouse=True)
    def setup_controller(self) -> None:
        ctrl = ReachyController(sim=True)
        asyncio.get_event_loop().run_until_complete(ctrl.connect())
        vision_tools.set_controller(ctrl)

    def test_capture_frame_sim(self) -> None:
        tool = vision_tools.CaptureFrameTool()
        result = tool._run()
        assert "simulation" in result.lower() or "no frame" in result.lower()

    def test_describe_scene_sim(self) -> None:
        tool = vision_tools.DescribeSceneTool()
        result = tool._run(question="What do you see?")
        assert "simulation" in result.lower() or "cannot" in result.lower()
