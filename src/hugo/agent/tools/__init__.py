"""The tool seam, and the one place the tool set is registered.

`Tool` is a Protocol, not a base class: HUGO's layers meet at Protocols
with no inheritance (see voice/loop.py's `Thinker`), so a tool is anything
carrying an OpenAI tool schema and an async `invoke`, and a test double
needs only those two. The schema already carries the name, so `ToolLoop`
derives both the `tools=` list it sends and the name -> implementation map
it dispatches through from the collection, and never learns a tool's name.

Failures stay *values* on this path, as they already were — an anticipated
failure becomes text the model reads on the next pass and paraphrases
aloud. `ToolFailure` adds one bit: whether another attempt could plausibly
go differently. Only the tool can know that (a timeout can, a rejected
credential cannot), which is why classification lives with the tool and
every transport's vocabulary — httpx exceptions, sqlite exceptions — stays
out of the dispatch layer.

`build_tools` is the registration point: one line per capability. A tool
whose dependency is missing is simply not built, so its schema never
reaches the model and the model never calls something that can't work
(docs/adr/0006).
"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from openai.types.chat import ChatCompletionToolParam
from pydantic import BaseModel, ValidationError

from hugo.config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolFailure:
    """A failure the tool anticipated, written to be spoken.

    `text` becomes the `role: tool` message, so its audience is a model
    that will paraphrase it aloud: no exception class names, no URLs, no
    status codes — the same discipline as mood tags and reasoning traces
    (CONTEXT.md). `retryable` says whether a second attempt could go
    differently; the turn loop honours it, the tool decides it.
    """

    text: str
    retryable: bool


class Tool(Protocol):
    """A capability the model can call: its schema, and how to run it."""

    schema: ChatCompletionToolParam

    async def invoke(self, arguments: dict[str, Any]) -> str | ToolFailure: ...


def schema_from(name: str, description: str, args: type[BaseModel]) -> ChatCompletionToolParam:
    """Builds the wire schema for a tool from its pydantic args model.

    Args models stay FLAT — no nested `BaseModel`. `model_json_schema()`
    emits `$defs`/`$ref` for those, and `$ref` is not reliably handled
    downstream (it is also the lossy corner of the MCP -> OpenAI schema
    mapping). A flat model renders as a plain JSON Schema object, which is
    what the chat template wants.
    """
    parameters: dict[str, Any] = args.model_json_schema()
    # pydantic titles the model class and every field ("WebSearchArgs",
    # "Query"). Those render into the prompt as noise carrying Python names,
    # and the hand-written schemas this replaces never had them — so the
    # generated schema stays what the model already saw.
    parameters.pop("title", None)
    for field in parameters.get("properties", {}).values():
        field.pop("title", None)
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


def parse_args[ArgsT: BaseModel](
    model: type[ArgsT], arguments: dict[str, Any]
) -> ArgsT | ToolFailure:
    """Validates a call's arguments, or reports why they were wrong.

    Nothing validates arguments before this: HUGO never sets `tool_choice`
    or `strict`, so vLLM takes its unconstrained path and extracts
    arguments from raw text without checking them against the schema. Bad
    arguments are a real, expected outcome, and they cannot go differently
    on a retry — the model has to change them.
    """
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        return ToolFailure(_readable(exc), retryable=False)


def _readable(exc: ValidationError) -> str:
    """Compacts a ValidationError to one plain sentence.

    "content: Field required" is the ceiling of detail — this string gets
    spoken, so no tracebacks and no model dumps.
    """
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['msg']}"
        for error in exc.errors()
    )
    return f"those arguments weren't right — {problems}."


def build_tools(config: Config) -> list[Tool]:
    """Assembles the tool set from what is actually available.

    A missing credential disables one capability with a warning instead of
    vetoing startup (docs/adr/0006, reversing the old fail-fast in
    `orchestrator.run`): the robot boots, and a typo'd `~/.hugo_secrets`
    surfaces as a journald warning plus a spoken "I can't search right
    now" rather than a service that won't start. That is also the rule an
    unreachable MCP server needs next round.
    """
    # Deferred: every tool module imports the seam from this package, so a
    # module-level import here would be a cycle.
    from hugo.agent.tools.web_search import WebSearchTool

    tools: list[Tool] = []
    if config.tavily_api_key:
        tools.append(WebSearchTool(config.tavily_api_key))
    else:
        logger.warning("HUGO_TAVILY_API_KEY is not set — web search disabled")
    return tools
