"""Reading back what HUGO wrote down, newest first.

Within one conversation HUGO needs none of this — history is append-only for
the life of the process. The store earns its keep across restarts, which is
the case this tool exists for.

Two decisions shape the output. Facts come back newest-first, which is the
whole of "the newest thing you said wins": a correction was saved as a new
row, so the model reads 9:45 before it ever reads 9:30 and the stale value
never becomes the answer. And a query that matches nothing falls back to the
whole store rather than reporting nothing — a filter that silently omits a
fact the user watched HUGO write down produces "you never told me that",
which is exactly the failure the audible-write promise exists to prevent.
Both paths are capped, so the worst case is bounded.

Timestamps are rendered in the configured zone, not UTC as stored: this
string is about to be spoken, and reading a fact saved at 5:40 PM back as
"9:40 PM" is the same confidently-wrong answer the host-clock version of
get_current_time shipped (live, 2026-08-10).
"""

import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from hugo.agent.tools import ToolFailure, parse_args, schema_from
from hugo.memory.models import Fact
from hugo.memory.store import MemoryStore

# The newest 50, on both the matched and the fallback path. A conclusion, not
# a knob: it is comfortably more than a single user's standing facts and
# comfortably less than a context-length problem. The store outgrowing it is
# the same threshold at which FTS5 and bounding conversation history both
# stop being deferrable — one problem, met once.
_RECALL_LIMIT = 50


class RecallFactsArgs(BaseModel):
    # Defaulted rather than required: "what do you know about me" is a real
    # thing to say, and a required field would answer it with a validation
    # failure and burn an LLM pass before the model thought to pass "".
    query: str = Field(
        default="",
        description=(
            "Words to look for, in the user's own phrasing. Matching is "
            "loose and a query that matches nothing returns everything, so "
            "guessing costs nothing. Leave it empty to list what you know."
        ),
    )


class RecallFactsTool:
    schema = schema_from(
        "recall_facts",
        "Look up what the user told you about themselves in earlier "
        "conversations. Call this whenever a question depends on something "
        "they said before -- a meeting time, a preference, a name, a plan -- "
        "rather than guessing or saying you don't know.",
        RecallFactsArgs,
    )

    def __init__(self, store: MemoryStore, timezone: str) -> None:
        self._store = store
        # Resolved at construction, so a config typo is a startup error
        # rather than HUGO apologising mid-sentence.
        self._zone = ZoneInfo(timezone)

    async def invoke(self, arguments: dict[str, Any]) -> str | ToolFailure:
        args = parse_args(RecallFactsArgs, arguments)
        if isinstance(args, ToolFailure):
            return args
        terms = args.query.lower().split()
        try:
            matches = await self._store.search_facts(terms, _RECALL_LIMIT)
            if matches:
                return self._render(matches)
            # Nothing matched. An empty query already asked for everything,
            # so only a real filter needs the second read.
            everything = await self._store.search_facts([], _RECALL_LIMIT) if terms else []
        except sqlite3.OperationalError:
            return ToolFailure("your notes were busy just then.", retryable=True)
        except sqlite3.Error:
            return ToolFailure("your notes couldn't be read.", retryable=False)
        if not everything:
            return "Nothing has been saved about the user yet."
        return (
            f"No facts matched '{args.query}'. Everything I know, newest "
            f"first:\n{self._render(everything)}"
        )

    def _render(self, facts: list[Fact]) -> str:
        # Written to be paraphrased aloud: the date and time by name, no ISO
        # strings, no ids. Newest line first, so the reading order carries
        # which statement supersedes which.
        return "\n".join(
            f"{fact.content} ({fact.created_at.astimezone(self._zone):%-d %B, %-I:%M %p})"
            for fact in facts
        )
