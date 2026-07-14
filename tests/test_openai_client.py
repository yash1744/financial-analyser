"""Unit tests for the OpenAI adapter: wire-format translation in both
directions and streamed tool-call accumulation, with a stubbed SDK client
(no network)."""

import json

import httpx
import openai
import pytest
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
)
from openai.types.chat.chat_completion import Choice

from app.ai.exceptions import LLMRateLimitError
from app.ai.openai_client import OpenAILLMClient
from app.ai.schemas import (
    ChatMessage,
    ResponseEnd,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from app.core.config import Settings


def make_settings() -> Settings:
    return Settings(openai_api_key="test", openai_model="gpt-5.1")


class StubCompletions:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        if kwargs.get("stream"):
            async def gen():
                for chunk in self.result:
                    yield chunk
            return gen()
        return self.result


class StubClient:
    def __init__(self, result):
        self.completions = StubCompletions(result)

    @property
    def chat(self):
        return self


def completion(message: ChatCompletionMessage, finish_reason: str) -> ChatCompletion:
    return ChatCompletion(
        id="cmpl-1",
        model="gpt-5.1",
        object="chat.completion",
        created=0,
        choices=[Choice(index=0, message=message, finish_reason=finish_reason)],
    )


def chunk(delta: dict, finish_reason: str | None = None) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "cmpl-1",
            "model": "gpt-5.1",
            "object": "chat.completion.chunk",
            "created": 0,
            "choices": [
                {"index": 0, "delta": delta, "finish_reason": finish_reason}
            ],
        }
    )


TOOLS = [
    {
        "name": "get_spending_summary",
        "description": "Spending summary",
        "input_schema": {"type": "object", "properties": {}},
    }
]


async def test_complete_translates_wire_format_both_ways():
    message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_spending_summary",
                    "arguments": '{"start_date": "2026-07-01"}',
                },
            }
        ],
    )
    stub = StubClient(completion(message, "tool_calls"))
    client = OpenAILLMClient(client=stub, settings=make_settings())

    history = [
        ChatMessage.text("user", "how much did I spend?"),
        ChatMessage(
            role="assistant",
            content=[
                ThinkingBlock(raw={"provider": "other"}),  # must be dropped
                TextBlock(text="Let me check."),
                ToolUseBlock(id="call_0", name="get_spending_summary", input={}),
            ],
        ),
        ChatMessage(
            role="tool",
            content=[
                ToolResultBlock(
                    tool_use_id="call_0", content='{"total": "1.00"}'
                ),
                ToolResultBlock(
                    tool_use_id="call_0b", content="boom", is_error=True
                ),
            ],
        ),
    ]
    response = await client.complete(system="sys", messages=history, tools=TOOLS)

    # request side
    sent = stub.completions.kwargs
    assert sent["model"] == "gpt-5.1"
    assert sent["max_completion_tokens"] == 4096
    assert sent["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_spending_summary",
                "description": "Spending summary",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    wire = sent["messages"]
    assert wire[0] == {"role": "system", "content": "sys"}
    assert wire[1] == {"role": "user", "content": "how much did I spend?"}
    assert wire[2]["role"] == "assistant"
    assert wire[2]["content"] == "Let me check."
    assert wire[2]["tool_calls"][0]["function"]["name"] == "get_spending_summary"
    assert json.loads(wire[2]["tool_calls"][0]["function"]["arguments"]) == {}
    # tool results: one wire message each, errors prefixed
    assert wire[3] == {
        "role": "tool", "tool_call_id": "call_0", "content": '{"total": "1.00"}',
    }
    assert wire[4] == {
        "role": "tool", "tool_call_id": "call_0b", "content": "Error: boom",
    }

    # response side
    assert response.stop_reason == "tool_use"
    (call,) = response.tool_calls
    assert call.id == "call_1"
    assert call.name == "get_spending_summary"
    assert call.arguments == {"start_date": "2026-07-01"}


async def test_stream_accumulates_text_and_tool_calls():
    chunks = [
        chunk({"role": "assistant", "content": "Check"}),
        chunk({"content": "ing…"}),
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_9",
                        "type": "function",
                        "function": {"name": "get_spending_summary", "arguments": ""},
                    }
                ]
            }
        ),
        chunk(
            {
                "tool_calls": [
                    {"index": 0, "function": {"arguments": '{"start_'}}
                ]
            }
        ),
        chunk(
            {
                "tool_calls": [
                    {"index": 0, "function": {"arguments": 'date": "2026-07-01"}'}}
                ]
            }
        ),
        chunk({}, finish_reason="tool_calls"),
    ]
    client = OpenAILLMClient(client=StubClient(chunks), settings=make_settings())

    events = [
        event
        async for event in client.stream(system="sys", messages=[], tools=TOOLS)
    ]
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Check", "ing…"]

    final = events[-1]
    assert isinstance(final, ResponseEnd)
    assert final.response.text == "Checking…"
    assert final.response.stop_reason == "tool_use"
    (call,) = final.response.tool_calls
    assert call.id == "call_9"
    assert call.arguments == {"start_date": "2026-07-01"}


async def test_malformed_tool_arguments_become_empty_dict():
    message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_spending_summary", "arguments": "{oops"},
            }
        ],
    )
    client = OpenAILLMClient(
        client=StubClient(completion(message, "tool_calls")),
        settings=make_settings(),
    )
    response = await client.complete(system="s", messages=[], tools=TOOLS)
    assert response.tool_calls[0].arguments == {}


def test_get_llm_client_selects_provider():
    from app.ai.exceptions import LLMConfigurationError
    from app.ai.llm_client import AnthropicLLMClient
    from app.api.deps import get_llm_client

    openai_settings = Settings(llm_provider="openai", openai_api_key="k")
    assert isinstance(get_llm_client(openai_settings), OpenAILLMClient)

    anthropic_settings = Settings(anthropic_api_key="k")
    assert isinstance(get_llm_client(anthropic_settings), AnthropicLLMClient)

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        get_llm_client(Settings(llm_provider="openai"))
    with pytest.raises(LLMConfigurationError, match="ANTHROPIC_API_KEY"):
        get_llm_client(Settings())


async def test_sdk_errors_map_to_typed_hierarchy():
    response = httpx.Response(
        status_code=429, request=httpx.Request("POST", "http://test")
    )
    error = openai.RateLimitError("rate limited", response=response, body=None)
    client = OpenAILLMClient(client=StubClient(error), settings=make_settings())
    with pytest.raises(LLMRateLimitError):
        await client.complete(system="s", messages=[], tools=[])
