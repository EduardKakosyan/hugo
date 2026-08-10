"""Tests the one tool that cannot fail. What's worth pinning is the schema
shape (a no-argument tool still has to render as a plain JSON Schema object)
and that the answer is written to be spoken rather than parsed."""

import re
from datetime import datetime

from hugo.agent.tools.current_time import CurrentTimeTool


def test_schema_is_a_flat_object_with_no_parameters() -> None:
    """No $defs/$ref: pydantic's title and the nested-model machinery are
    both noise the chat template doesn't want, and $ref is the lossy corner
    of the MCP -> OpenAI schema mapping."""
    function = CurrentTimeTool.schema["function"]

    assert function["name"] == "get_current_time"
    assert function["parameters"] == {"type": "object", "properties": {}}


async def test_answer_names_the_weekday_date_and_zone() -> None:
    now = datetime.now().astimezone()

    answer = await CurrentTimeTool().invoke({})

    # Spoken register: the weekday and month by name, no zero padding, no
    # ISO string, and the zone the host is actually in (the answer is only
    # as right as dgx1's clock -- see the module docstring).
    assert now.strftime("%A") in answer
    assert now.strftime("%B") in answer
    assert str(now.day) in answer
    assert str(now.year) in answer
    assert answer.endswith(str(now.tzinfo))
    assert not re.search(r"\d{4}-\d{2}-\d{2}", answer)


async def test_extra_arguments_are_ignored_rather_than_rejected() -> None:
    """The model can pass something anyway; a clock has nothing to reject."""
    assert await CurrentTimeTool().invoke({"timezone": "Europe/Paris"})
