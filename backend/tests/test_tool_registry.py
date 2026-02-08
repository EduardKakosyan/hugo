"""Tests for the tool registry."""

from typing import Any

from src.bridge.tool_registry import ToolDef, ToolRegistry


async def _dummy_handler(**kwargs: Any) -> str:
    return "ok"


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = ToolDef(
            name="test", description="A test tool", handler=_dummy_handler, category="general"
        )
        reg.register(tool)
        assert reg.get("test") is tool

    def test_unregister(self) -> None:
        reg = ToolRegistry()
        tool = ToolDef(
            name="test", description="A test tool", handler=_dummy_handler, category="general"
        )
        reg.register(tool)
        reg.unregister("test")
        assert reg.get("test") is None

    def test_list_by_category(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDef(name="v1", description="", handler=_dummy_handler, category="vision")
        )
        reg.register(
            ToolDef(name="t1", description="", handler=_dummy_handler, category="text")
        )
        vision_tools = reg.list_tools(category="vision")
        assert len(vision_tools) == 1
        assert vision_tools[0].name == "v1"

    def test_enable_disable(self) -> None:
        reg = ToolRegistry()
        tool = ToolDef(
            name="test", description="", handler=_dummy_handler, category="general"
        )
        reg.register(tool)

        reg.disable("test")
        assert reg.list_tools(enabled_only=True) == []

        reg.enable("test")
        assert len(reg.list_tools(enabled_only=True)) == 1

    def test_list_all_includes_disabled(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDef(name="a", description="", handler=_dummy_handler, category="general")
        )
        reg.register(
            ToolDef(
                name="b",
                description="",
                handler=_dummy_handler,
                category="general",
                enabled=False,
            )
        )
        assert len(reg.list_tools(enabled_only=False)) == 2
        assert len(reg.list_tools(enabled_only=True)) == 1

    def test_get_nonexistent_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_unregister_nonexistent_is_noop(self) -> None:
        reg = ToolRegistry()
        reg.unregister("nonexistent")  # Should not raise
