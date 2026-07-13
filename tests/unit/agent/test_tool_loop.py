from hugo.agent.tool_loop import DEFAULT_SYSTEM_PROMPT, ToolLoop


class _FakeLlmClient:
    def __init__(self, response: str = "hi there") -> None:
        self.response = response
        self.seen_messages: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.seen_messages.append(list(messages))
        return self.response


async def test_think_returns_the_llm_response() -> None:
    llm = _FakeLlmClient(response="hello!")
    loop = ToolLoop(llm)  # type: ignore[arg-type]

    result = await loop.think("hi hugo")

    assert result == "hello!"


async def test_think_sends_system_prompt_then_user_turn() -> None:
    llm = _FakeLlmClient()
    loop = ToolLoop(llm)  # type: ignore[arg-type]

    await loop.think("what time is it")

    sent = llm.seen_messages[0]
    assert sent[0] == {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
    assert sent[1] == {"role": "user", "content": "what time is it"}


async def test_conversation_history_accumulates_across_turns() -> None:
    llm = _FakeLlmClient(response="ok")
    loop = ToolLoop(llm)  # type: ignore[arg-type]

    await loop.think("first question")
    await loop.think("second question")

    second_call_messages = llm.seen_messages[1]
    roles_and_content = [(m["role"], m["content"]) for m in second_call_messages]
    assert roles_and_content == [
        ("system", DEFAULT_SYSTEM_PROMPT),
        ("user", "first question"),
        ("assistant", "ok"),
        ("user", "second question"),
    ]
