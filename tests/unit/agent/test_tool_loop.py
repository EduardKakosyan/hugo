from typing import Any

from hugo.agent.tool_loop import DEFAULT_SYSTEM_PROMPT, ToolLoop


class _FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id: str, name: str, arguments: str) -> None:
        self.id = id
        self.type = "function"
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content: str | None, tool_calls: list[_FakeToolCall] | None) -> None:
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {"role": "assistant"}
        if self.content is not None:
            data["content"] = self.content
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
        return data


class _FakeLlmClient:
    """Returns each scripted response once, then keeps returning the last
    one -- lets a test script "always call a tool" with a single-item list."""

    def __init__(self, responses: list[_FakeMessage]) -> None:
        self._responses = list(responses)
        self.seen_messages: list[list[dict[str, Any]]] = []
        self.seen_tools: list[Any] = []

    async def complete_with_tools(self, messages: list[dict[str, Any]], tools: Any) -> _FakeMessage:
        self.seen_messages.append(list(messages))
        self.seen_tools.append(tools)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class _FakeWebSearchTool:
    def __init__(self, result: str = "search result") -> None:
        self.result = result
        self.queries: list[str] = []

    async def search(self, query: str) -> str:
        self.queries.append(query)
        return self.result


async def test_think_returns_the_llm_response() -> None:
    llm = _FakeLlmClient([_FakeMessage(content="hello!", tool_calls=None)])
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    result = await loop.think("hi hugo")

    assert result == "hello!"


async def test_think_sends_system_prompt_then_user_turn() -> None:
    llm = _FakeLlmClient([_FakeMessage(content="hi there", tool_calls=None)])
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    await loop.think("what time is it")

    sent = llm.seen_messages[0]
    assert sent[0] == {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
    assert sent[1] == {"role": "user", "content": "what time is it"}


async def test_conversation_history_accumulates_across_turns() -> None:
    llm = _FakeLlmClient(
        [
            _FakeMessage(content="ok", tool_calls=None),
            _FakeMessage(content="ok2", tool_calls=None),
        ]
    )
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    await loop.think("first question")
    await loop.think("second question")

    second_call_messages = llm.seen_messages[1]
    roles = [m["role"] for m in second_call_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert second_call_messages[2]["content"] == "ok"
    assert second_call_messages[3] == {"role": "user", "content": "second question"}


async def test_think_dispatches_web_search_tool_call_and_continues() -> None:
    tool_call = _FakeToolCall(id="call_1", name="web_search", arguments='{"query": "weather"}')
    first = _FakeMessage(content=None, tool_calls=[tool_call])
    second = _FakeMessage(content="It's sunny.", tool_calls=None)
    llm = _FakeLlmClient([first, second])
    web_search = _FakeWebSearchTool(result="sunny today")
    loop = ToolLoop(llm, web_search=web_search)  # type: ignore[arg-type]

    result = await loop.think("what's the weather")

    assert result == "It's sunny."
    assert web_search.queries == ["weather"]
    second_call_messages = llm.seen_messages[1]
    tool_message = next(m for m in second_call_messages if m.get("role") == "tool")
    assert tool_message == {"role": "tool", "tool_call_id": "call_1", "content": "sunny today"}


async def test_think_falls_back_after_max_tool_iterations() -> None:
    tool_call = _FakeToolCall(id="call_1", name="web_search", arguments='{"query": "x"}')
    always_tool_call = _FakeMessage(content=None, tool_calls=[tool_call])
    llm = _FakeLlmClient([always_tool_call])
    loop = ToolLoop(llm, web_search=_FakeWebSearchTool())  # type: ignore[arg-type]

    result = await loop.think("loop forever")

    assert "trouble" in result.lower()


def test_speechify_strips_markdown_and_bullets() -> None:
    from hugo.agent.tool_loop import speechify

    assert speechify("**Bold** and `code` and #tag") == "Bold and code and tag"
    assert (
        speechify("Here you go:\n- first thing\n- second thing\n1. third")
        == "Here you go: first thing second thing third"
    )
    assert speechify("  plain sentence stays put.  ") == "plain sentence stays put."
