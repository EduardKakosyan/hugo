"""The date and time, from the host clock.

The model has no idea what day it is: without this, "this afternoon",
"tomorrow" and "how long ago" resolve against whatever the training data
implied, which is why this trivial-looking tool is a hard prerequisite for
every calendar-shaped question rather than filler.

The zone comes from Config.timezone, not the host. Reading the host's zone
was tried first and shipped a wrong answer within the hour: dgx1 runs on
Etc/UTC, so HUGO announced "11:36 PM, UTC" at 8:36 PM in Halifax (live,
2026-08-10). Fixing that at the host would mean moving the clock for every
other user of a shared box, so the robot carries its own location — which
also makes the rendering testable without touching the machine's clock.

No arguments (one robot, one place) and no failure path: there is nothing
here to time out, reject, or misread, so nothing to classify. A bad zone
name is a startup error, not a tool failure — it would be wrong to let HUGO
apologise mid-sentence for a typo in the config.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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

    def __init__(self, timezone: str) -> None:
        # Resolved once, at construction: an unknown zone name raises here,
        # during startup, rather than inside a turn.
        self._zone = ZoneInfo(timezone)

    async def invoke(self, arguments: dict[str, Any]) -> str:
        # Spelled out the way a person says it, because the model is about
        # to say it: no ISO strings, no zero padding, no UTC offsets. %Z
        # renders the zone's current abbreviation, so it follows the zone
        # into and out of daylight saving on its own (ADT / AST).
        return datetime.now(self._zone).strftime("%A, %-d %B %Y, %-I:%M %p, %Z")
