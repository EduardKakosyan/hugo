"""The date and time, from the host clock.

The model has no idea what day it is: without this, "this afternoon",
"tomorrow" and "how long ago" resolve against whatever the training data
implied, which is why this trivial-looking tool is a hard prerequisite for
every calendar-shaped question rather than filler.

It reads the *host's* zone (`astimezone()` with no argument), which makes
dgx1's timezone a deployment dependency of a user-visible answer for the
first time — worth confirming with `timedatectl` on the box rather than
discovering through a wrong "this afternoon".

No arguments (one robot, one place) and no failure path: there is nothing
here to time out, reject, or misread, so nothing to classify.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hugo.agent.tools import schema_from


class CurrentTimeArgs(BaseModel):
    # No arguments: one robot, one place, so there is no timezone to pass.
    # Renders as {"type": "object", "properties": {}} -- kept as a comment
    # rather than a docstring, which pydantic would turn into a schema
    # `description` the model has to read.
    pass


class CurrentTimeTool:
    schema = schema_from(
        "get_current_time",
        "Get the current date, day of the week, and local time. Call this "
        "before answering anything that depends on today, tomorrow, this "
        "week, or how long ago something happened -- you have no other way "
        "to know what day it is.",
        CurrentTimeArgs,
    )

    async def invoke(self, arguments: dict[str, Any]) -> str:
        # Spelled out the way a person says it, because the model is about
        # to say it: no ISO strings, no zero padding, no UTC offsets.
        now = datetime.now().astimezone()
        return now.strftime("%A, %-d %B %Y, %-I:%M %p, ") + str(now.tzinfo)
