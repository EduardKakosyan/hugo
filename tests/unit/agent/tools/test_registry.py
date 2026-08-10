"""Tests build_tools -- the registration point. "How many tools does HUGO
have" is a data question, so it gets asserted as data: what the set contains
for a given Config, and that a missing credential costs a capability rather
than raising (docs/adr/0006)."""

import logging

import pytest

from hugo.agent.tools import Tool, build_tools
from hugo.config import Config


def _names(tools: list[Tool]) -> list[str]:
    return [tool.schema["function"]["name"] for tool in tools]


def test_build_tools_includes_web_search_when_a_key_is_configured() -> None:
    tools = build_tools(Config(tavily_api_key="test-key"))

    assert "web_search" in _names(tools)


def test_build_tools_omits_web_search_and_warns_without_a_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reversal of the old startup RuntimeError: a typo'd
    ~/.hugo_secrets is a journald warning, not a robot that won't boot."""
    with caplog.at_level(logging.WARNING):
        tools = build_tools(Config(tavily_api_key=None))

    assert "web_search" not in _names(tools)
    assert "web search disabled" in caplog.text


def test_schema_names_are_unique() -> None:
    """Dispatch is a dict keyed on the schema name, so a duplicate would
    silently shadow a tool rather than fail."""
    names = _names(build_tools(Config(tavily_api_key="test-key")))

    assert len(names) == len(set(names))


def test_every_tool_declares_an_object_parameters_schema() -> None:
    for tool in build_tools(Config(tavily_api_key="test-key")):
        parameters = tool.schema["function"]["parameters"]
        assert parameters["type"] == "object"  # type: ignore[index]
        # $ref/$defs are the lossy corner of the schema mapping and are not
        # reliably handled downstream — args models stay flat.
        assert "$defs" not in repr(parameters) and "$ref" not in repr(parameters)
