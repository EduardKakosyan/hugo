"""Tests the one tool that cannot fail. What's worth pinning is the schema
shape (a no-argument tool still has to render as a plain JSON Schema object)
and that the answer is written to be spoken rather than parsed."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from hugo.agent.tools.current_time import CurrentTimeTool

_ZONE = "America/Halifax"


def test_schema_is_a_flat_object_with_no_parameters() -> None:
    """No $defs/$ref: pydantic's title and the nested-model machinery are
    both noise the chat template doesn't want, and $ref is the lossy corner
    of the MCP -> OpenAI schema mapping."""
    function = CurrentTimeTool.schema["function"]

    assert function["name"] == "get_current_time"
    assert function["parameters"] == {"type": "object", "properties": {}}


async def test_answer_names_the_weekday_date_and_zone() -> None:
    now = datetime.now(ZoneInfo(_ZONE))

    answer = await CurrentTimeTool(_ZONE).invoke({})

    # Spoken register: the weekday and month by name, no zero padding, no
    # ISO string.
    assert now.strftime("%A") in answer
    assert now.strftime("%B") in answer
    assert str(now.day) in answer
    assert str(now.year) in answer
    assert not re.search(r"\d{4}-\d{2}-\d{2}", answer)


async def test_answer_is_in_the_configured_zone_not_the_hosts() -> None:
    """The bug this tool shipped with: dgx1 sits on Etc/UTC, so reading the
    host zone had HUGO announcing 11:36 PM at 8:36 PM in Halifax. Two zones
    far enough apart that the rendered hour cannot coincide."""
    answer = await CurrentTimeTool("Pacific/Kiritimati").invoke({})

    expected = datetime.now(ZoneInfo("Pacific/Kiritimati"))
    assert expected.strftime("%-I:%M %p") in answer
    # The abbreviation follows the zone, so DST needs no code of its own.
    assert answer.endswith(expected.strftime("%Z"))


async def test_a_bad_zone_fails_at_construction_not_mid_turn() -> None:
    """A config typo must not surface as HUGO apologising mid-sentence."""
    with pytest.raises(ZoneInfoNotFoundError):
        CurrentTimeTool("Not/AZone")


async def test_extra_arguments_are_ignored_rather_than_rejected() -> None:
    """The model can pass something anyway; a clock has nothing to reject."""
    assert await CurrentTimeTool(_ZONE).invoke({"timezone": "Europe/Paris"})
