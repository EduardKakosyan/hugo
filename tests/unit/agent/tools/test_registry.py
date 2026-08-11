"""Tests build_tools -- the registration point. "How many tools does HUGO
have" is a data question, so it gets asserted as data: what the set contains
for a given Config, and that a missing credential costs a capability rather
than raising (docs/adr/0006)."""

import logging
from pathlib import Path

import pytest

from hugo.agent.tools import Tool, build_tools
from hugo.config import Config
from hugo.memory.store import MemoryStore


def _names(tools: list[Tool]) -> list[str]:
    return [tool.schema["function"]["name"] for tool in tools]


def _store(tmp_path: Path) -> MemoryStore:
    # Constructing a store does no I/O, and build_tools only hands it to
    # constructors — nothing here needs the DB to exist.
    return MemoryStore(tmp_path / "memory.db")


def test_build_tools_includes_web_search_when_a_key_is_configured(tmp_path: Path) -> None:
    tools = build_tools(Config(tavily_api_key="test-key"), _store(tmp_path))

    assert "web_search" in _names(tools)


def test_build_tools_omits_web_search_and_warns_without_a_key(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """The reversal of the old startup RuntimeError: a typo'd
    ~/.hugo_secrets is a journald warning, not a robot that won't boot."""
    with caplog.at_level(logging.WARNING):
        tools = build_tools(Config(tavily_api_key=None), _store(tmp_path))

    assert "web_search" not in _names(tools)
    assert "web search disabled" in caplog.text


def test_the_memory_tools_are_unconditional(tmp_path: Path) -> None:
    """The store was constructed and initialize()d at every start and read by
    nothing; these two are its first consumers."""
    names = _names(build_tools(Config(tavily_api_key=None), _store(tmp_path)))

    assert "remember_fact" in names
    assert "recall_facts" in names


def test_schema_names_are_unique(tmp_path: Path) -> None:
    """Dispatch is a dict keyed on the schema name, so a duplicate would
    silently shadow a tool rather than fail."""
    names = _names(build_tools(Config(tavily_api_key="test-key"), _store(tmp_path)))

    assert len(names) == len(set(names))


def test_every_tool_declares_an_object_parameters_schema(tmp_path: Path) -> None:
    for tool in build_tools(Config(tavily_api_key="test-key"), _store(tmp_path)):
        parameters = tool.schema["function"]["parameters"]
        assert parameters["type"] == "object"  # type: ignore[index]
        # $ref/$defs are the lossy corner of the schema mapping and are not
        # reliably handled downstream — args models stay flat.
        assert "$defs" not in repr(parameters) and "$ref" not in repr(parameters)
