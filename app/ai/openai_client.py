"""LLMClient adapter for the OpenAI Chat Completions API.

Together with llm_client.py (Anthropic), these are the only modules that
import a provider SDK. The adapter translates between the provider-neutral
types in app/ai/schemas.py and OpenAI's wire format:

- our system prompt        → a leading "system" message
- ToolUseBlock             → assistant message tool_calls entries
- ToolResultBlock          → one "tool" message per result (OpenAI requires
                             a separate message per tool_call_id)
- {name, description, input_schema} tool definitions
                           → {"type": "function", "function": {...}}
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from app.ai.exceptions import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.ai.schemas import (
    ChatMessage,
    LLMResponse,
    LLMStreamEvent,
    ResponseEnd,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ToolCall,
    ToolResultBlock,
    ToolUseBlock,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

_STOP_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def _translate_error(exc: Exception) -> Exception:
    """Map SDK exceptions onto our typed hierarchy (most specific first)."""
    if isinstance(exc, openai.AuthenticationError):
        return LLMAuthError("LLM provider rejected our credentials")
    if isinstance(exc, openai.RateLimitError):
        return LLMRateLimitError("LLM provider rate limit exceeded")
    if isinstance(exc, openai.APITimeoutError):
        return LLMTimeoutError("LLM request timed out")
    if isinstance(exc, openai.APIStatusError):
        return LLMError(f"LLM provider error (status {exc.status_code})")
    if isinstance(exc, openai.APIConnectionError):
        return LLMError("could not reach the LLM provider")
    return exc


def _parse_arguments(raw: str) -> dict[str, Any]:
    """Tool arguments arrive as a JSON string; a malformed one becomes {}
    so the registry can reject the call as a readable error result."""
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class OpenAILLMClient:
    """LLMClient adapter for the OpenAI Chat Completions API."""

    def __init__(self, client: AsyncOpenAI, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    # --- provider-neutral ↔ wire format ---

    @staticmethod
    def _to_wire_messages(
        system: str, messages: list[ChatMessage]
    ) -> list[dict[str, Any]]:
        wire: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in messages:
            if message.role == "tool":
                # one wire message per tool result
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        content = block.content
                        if block.is_error:
                            content = f"Error: {content}"
                        wire.append(
                            {
                                "role": "tool",
                                "tool_call_id": block.tool_use_id,
                                "content": content,
                            }
                        )
                continue

            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    if block.text.strip():
                        text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        {
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        }
                    )
                elif isinstance(block, ThinkingBlock):
                    # provider-specific reasoning state; OpenAI has no
                    # equivalent to replay, so it is dropped
                    continue
            entry: dict[str, Any] = {
                "role": message.role,
                "content": "\n".join(text_parts) or None,
            }
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if entry["content"] is None and not tool_calls:
                continue
            wire.append(entry)
        return wire

    @staticmethod
    def _to_wire_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _to_response(
        message: ChatCompletionMessage, finish_reason: str | None
    ) -> LLMResponse:
        content: list[Any] = []
        text = message.content or ""
        if text:
            content.append(TextBlock(text=text))
        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            if call.type != "function":
                continue
            arguments = _parse_arguments(call.function.arguments)
            content.append(
                ToolUseBlock(id=call.id, name=call.function.name, input=arguments)
            )
            tool_calls.append(
                ToolCall(id=call.id, name=call.function.name, arguments=arguments)
            )
        return LLMResponse(
            content=content,
            text=text,
            tool_calls=tool_calls,
            stop_reason=_STOP_REASONS.get(finish_reason or "stop", "end_turn"),
        )

    def _request_kwargs(
        self, system: str, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self._settings.openai_model,
            "max_completion_tokens": self._settings.llm_max_tokens,
            "messages": self._to_wire_messages(system, messages),
            "tools": self._to_wire_tools(tools),
        }

    # --- LLMClient interface ---

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        try:
            completion = await self._client.chat.completions.create(
                **self._request_kwargs(system, messages, tools)
            )
        except Exception as exc:
            raise _translate_error(exc) from exc
        choice = completion.choices[0]
        return self._to_response(choice.message, choice.finish_reason)

    async def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]:
        text_parts: list[str] = []
        # keyed by index: tool calls stream as fragments to accumulate
        calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        try:
            response = await self._client.chat.completions.create(
                **self._request_kwargs(system, messages, tools), stream=True
            )
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta is None:
                    continue
                if delta.content:
                    text_parts.append(delta.content)
                    yield TextDelta(text=delta.content)
                for fragment in delta.tool_calls or []:
                    call = calls.setdefault(
                        fragment.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if fragment.id:
                        call["id"] = fragment.id
                    if fragment.function:
                        call["name"] += fragment.function.name or ""
                        call["arguments"] += fragment.function.arguments or ""
        except Exception as exc:
            raise _translate_error(exc) from exc

        text = "".join(text_parts)
        content: list[Any] = [TextBlock(text=text)] if text else []
        tool_calls: list[ToolCall] = []
        for _, call in sorted(calls.items()):
            arguments = _parse_arguments(call["arguments"])
            content.append(
                ToolUseBlock(id=call["id"], name=call["name"], input=arguments)
            )
            tool_calls.append(
                ToolCall(id=call["id"], name=call["name"], arguments=arguments)
            )
        yield ResponseEnd(
            response=LLMResponse(
                content=content,
                text=text,
                tool_calls=tool_calls,
                stop_reason=_STOP_REASONS.get(finish_reason or "stop", "end_turn"),
            )
        )
