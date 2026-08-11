"""Writing something down — the only tool in the set with a side effect.

There is no magic word: the system prompt asks the model to judge what is
durable and save it unasked, so HUGO behaves the way a person would rather
than requiring the user to say "remember". The safeguard for that judgement
is that every write is *audible*, and this file is where that guarantee
starts: `invoke` returns the exact wording it committed, so the model speaks
the confirmation as part of the reply it was going to give anyway. Nothing
here authors speech — that would be a mechanism no MCP tool can supply, so
it would guard only the tools we hand-write.

A correction is a new row, never an edit (recall reads newest-first), so
there is no update path and no delete path here. `hugo forget` remains the
blunt reset.

sqlite's vocabulary is read here and nowhere else, per the seam's rule that
a tool classifies its own failures: a locked or busy database can go
differently in a second, anything else it raises cannot.
"""

import sqlite3
from typing import Any

from pydantic import BaseModel, Field

from hugo.agent.tools import ToolFailure, parse_args, schema_from
from hugo.memory.store import MemoryStore


class RememberFactArgs(BaseModel):
    content: str = Field(
        description=(
            "The fact to save, as one complete sentence in the user's own "
            "words -- it will be read back to them and stored verbatim."
        )
    )


class RememberFactTool:
    # The description carries the "you have no other memory" framing as
    # well as the system prompt, because at TEMPERATURE 1.0 the prompt
    # alone did not hold: measured on dgx1 2026-08-11, "Remember that my
    # standup is at 9:30" produced a bare "I'll remember that" on 3 runs
    # in 5. The schema is the text nearest the decision the model is
    # actually sampling, and "never say you'll remember without calling
    # this" names the exact wrong completion rather than describing the
    # right one.
    schema = schema_from(
        "remember_fact",
        "Save something durable the user told you about themselves -- a "
        "standing meeting time, a preference, a name, a deadline -- so you "
        "still know it after a restart. This is your ONLY memory: a fact "
        "you don't save here is gone the moment this conversation ends, so "
        "never reply that you'll remember something without calling this "
        "first -- that is a promise you cannot keep. Call it whenever the "
        "user asks you to remember something, and unasked when something "
        "durable comes up. Let passing chatter go. To correct an earlier "
        "fact, save the new version; nothing needs deleting.",
        RememberFactArgs,
    )

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def invoke(self, arguments: dict[str, Any]) -> str | ToolFailure:
        args = parse_args(RememberFactArgs, arguments)
        if isinstance(args, ToolFailure):
            return args
        try:
            fact = await self._store.add_fact(args.content)
        except sqlite3.OperationalError:
            # Locked or busy: a second attempt plausibly lands. A failed
            # write MUST be audible — HUGO saying "I've written that down"
            # over a write that didn't happen tells the user something false
            # about their own data, which they'd discover days later.
            return ToolFailure(
                "your notes were busy, so that didn't get written down.", retryable=True
            )
        except sqlite3.Error:
            return ToolFailure("that couldn't be written down.", retryable=False)
        # The exact stored wording, back to the model: it speaks the
        # confirmation in its own register, and the user hears what HUGO now
        # believes at the moment it happens.
        return f'Saved: "{fact.content}"'
