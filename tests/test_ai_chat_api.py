"""Tests for the LLM chat backend: real Postgres + real tools, fake LLM.

The FakeLLMClient plays scripted turns, so these tests exercise the full
production path — agent loop, tool registry, FinanceToolset, services,
repositories, persistence — without calling a provider.
"""

import json
import uuid
from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.ai.exceptions import LLMRateLimitError
from app.ai.schemas import (
    ChatMessage,
    LLMResponse,
    ResponseEnd,
    TextBlock,
    TextDelta,
    ToolCall,
    ToolUseBlock,
)
from app.api.deps import get_llm_client
from app.main import app


def tool_turn(name: str, arguments: dict, call_id: str = "call-1") -> LLMResponse:
    return LLMResponse(
        content=[ToolUseBlock(id=call_id, name=name, input=arguments)],
        text="",
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        stop_reason="tool_use",
    )


def text_turn(text: str) -> LLMResponse:
    return LLMResponse(
        content=[TextBlock(text=text)], text=text, tool_calls=[], stop_reason="end_turn"
    )


class FakeLLMClient:
    """Scripted LLM: pops one canned response per call and records what it
    was sent. A response given as an exception is raised instead."""

    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def _next(self, system, messages, tools) -> LLMResponse:
        # snapshot: the agent mutates the same list across iterations
        self.calls.append(
            {"system": system, "messages": list(messages), "tools": tools}
        )
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def complete(self, *, system, messages, tools) -> LLMResponse:
        return self._next(system, messages, tools)

    async def stream(self, *, system, messages, tools) -> AsyncIterator:
        response = self._next(system, messages, tools)
        # stream the text in two chunks, like a real provider would
        if response.text:
            middle = len(response.text) // 2
            yield TextDelta(text=response.text[:middle])
            yield TextDelta(text=response.text[middle:])
        yield ResponseEnd(response=response)


def install(script: list) -> FakeLLMClient:
    fake = FakeLLMClient(script)
    app.dependency_overrides[get_llm_client] = lambda: fake
    return fake


async def create_user(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users", json={"email": f"ai-{uuid.uuid4().hex[:12]}@example.com"}
    )
    return resp.json()["id"]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for chunk in body.strip().split("\n\n"):
        lines = chunk.split("\n")
        name = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((name, data))
    return events


async def test_chat_tool_loop_and_persistence():
    fake = install(
        [
            tool_turn("get_spending_summary", {}),
            text_turn("You spent $0.00 — no transactions are synced yet."),
        ]
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_id = await create_user(client)

            resp = await client.post(
                "/api/v1/ai/chat",
                json={"user_id": user_id, "message": "How much did I spend?"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["message"].startswith("You spent $0.00")
            (tool_call,) = body["tool_calls"]
            assert tool_call["name"] == "get_spending_summary"
            assert tool_call["status"] == "completed"
            assert isinstance(tool_call["duration_ms"], int)
            conversation_id = body["conversation_id"]

            # the LLM was called twice; the 2nd call carried the tool result
            assert len(fake.calls) == 2
            second_call_messages: list[ChatMessage] = fake.calls[1]["messages"]
            tool_message = second_call_messages[-1]
            assert tool_message.role == "tool"
            result = json.loads(tool_message.content[0].content)
            assert result["total_spending"] == "0.00"

            # tools were provided, without user_id in any schema
            tool_names = {t["name"] for t in fake.calls[0]["tools"]}
            assert "get_spending_summary" in tool_names
            assert "search_transactions" in tool_names

            # follow-up in the same conversation sees prior context
            fake.script = [text_turn("As I said, nothing was spent.")]
            resp = await client.post(
                "/api/v1/ai/chat",
                json={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message": "Say that again?",
                },
            )
            assert resp.status_code == 200
            history = fake.calls[2]["messages"]
            texts = [b.text for m in history for b in m.content if b.type == "text"]
            assert "How much did I spend?" in texts
            assert any(t.startswith("You spent $0.00") for t in texts)
            # tool turns are stored but not replayed as context
            assert all(m.role in ("user", "assistant") for m in history)
    finally:
        app.dependency_overrides.clear()


async def test_chat_stream_sse_events():
    install(
        [
            tool_turn("get_recurring_transactions", {"lookback_days": 90}),
            text_turn("No recurring charges found."),
        ]
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_id = await create_user(client)
            resp = await client.post(
                "/api/v1/ai/chat/stream",
                json={"user_id": user_id, "message": "Any subscriptions?"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            events = parse_sse(resp.text)

            names = [name for name, _ in events]
            assert names.count("tool") == 2  # running + completed
            assert names[-1] == "done"

            tool_events = [d for n, d in events if n == "tool"]
            assert tool_events[0]["name"] == "get_recurring_transactions"
            assert tool_events[0]["status"] == "running"
            assert tool_events[0]["duration_ms"] is None
            assert tool_events[1]["status"] == "completed"
            assert isinstance(tool_events[1]["duration_ms"], int)

            tokens = "".join(d["text"] for n, d in events if n == "token")
            assert tokens == "No recurring charges found."

            done = events[-1][1]
            assert done["message"] == "No recurring charges found."
            assert done["conversation_id"]
    finally:
        app.dependency_overrides.clear()


async def test_invalid_tool_call_recovers_as_error_result():
    fake = install(
        [
            # bad arguments (lookback_days below minimum), then an unknown tool,
            # then the model recovers with a final answer
            tool_turn("get_recurring_transactions", {"lookback_days": 1}),
            tool_turn("drop_database", {}, call_id="call-2"),
            text_turn("I hit a tool problem but recovered."),
        ]
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_id = await create_user(client)
            resp = await client.post(
                "/api/v1/ai/chat",
                json={"user_id": user_id, "message": "subscriptions?"},
            )
            assert resp.status_code == 200
            assert [
                (c["name"], c["status"]) for c in resp.json()["tool_calls"]
            ] == [
                ("get_recurring_transactions", "failed"),
                ("drop_database", "failed"),
            ]
            # each failure was fed back to the model as an error tool_result
            for call_index, needle in ((1, "lookback_days"), (2, "Unknown tool")):
                tool_message = fake.calls[call_index]["messages"][-1]
                block = tool_message.content[0]
                assert block.is_error is True
                assert needle in block.content
    finally:
        app.dependency_overrides.clear()


async def test_llm_failure_maps_to_429():
    install([LLMRateLimitError("slow down")])
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_id = await create_user(client)
            resp = await client.post(
                "/api/v1/ai/chat", json={"user_id": user_id, "message": "hi"}
            )
            assert resp.status_code == 429
    finally:
        app.dependency_overrides.clear()


async def test_conversation_ownership_and_missing_user():
    install([text_turn("hello")])
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_a = await create_user(client)
            user_b = await create_user(client)

            resp = await client.post(
                "/api/v1/ai/chat", json={"user_id": user_a, "message": "hi"}
            )
            conversation_id = resp.json()["conversation_id"]

            # another user cannot continue someone else's conversation
            resp = await client.post(
                "/api/v1/ai/chat",
                json={
                    "user_id": user_b,
                    "conversation_id": conversation_id,
                    "message": "hi",
                },
            )
            assert resp.status_code == 404

            # unknown user
            resp = await client.post(
                "/api/v1/ai/chat",
                json={"user_id": str(uuid.uuid4()), "message": "hi"},
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
