"""Provider-independent LLM client interface + the Anthropic implementation.

Provider SDKs are imported only by the adapters (this module and
app/ai/openai_client.py). Everything else speaks the provider-neutral
message/event types in app/ai/schemas.py, so adding a provider means
writing one new adapter and wiring it in get_llm_client.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

import anthropic
from anthropic import AsyncAnthropic

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


class LLMClient(Protocol):
    """What the agent needs from a chat-completion provider."""

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
    ) -> LLMResponse: ...

    def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]: ...


def _translate_error(exc: Exception) -> Exception:
    """Map SDK exceptions onto our typed hierarchy (most specific first)."""
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMAuthError("LLM provider rejected our credentials")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitError("LLM provider rate limit exceeded")
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMTimeoutError("LLM request timed out")
    if isinstance(exc, anthropic.APIStatusError):
        return LLMError(f"LLM provider error (status {exc.status_code})")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError("could not reach the LLM provider")
    return exc


class AnthropicLLMClient:
    """LLMClient adapter for the Anthropic Messages API."""

    def __init__(self, client: AsyncAnthropic, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    # --- provider-neutral ↔ wire format ---

    @staticmethod
    def _to_params(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        params: list[dict[str, Any]] = []
        for message in messages:
            blocks: list[dict[str, Any]] = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    if block.text.strip():  # provider rejects empty text
                        blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                elif isinstance(block, ToolResultBlock):
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "content": block.content,
                            "is_error": block.is_error,
                        }
                    )
                elif isinstance(block, ThinkingBlock):
                    # echoed back verbatim — required when continuing a
                    # turn on the same model
                    blocks.append(block.raw)
            if not blocks:
                continue
            # our "tool" role carries tool results; the wire role is "user"
            role = "user" if message.role == "tool" else message.role
            params.append({"role": role, "content": blocks})
        return params

    @staticmethod
    def _to_response(message: anthropic.types.Message) -> LLMResponse:
        content: list[Any] = []
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in message.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
                text_parts.append(block.text)
            elif block.type == "tool_use":
                content.append(
                    ToolUseBlock(id=block.id, name=block.name, input=block.input)
                )
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )
            elif block.type in ("thinking", "redacted_thinking"):
                content.append(ThinkingBlock(raw=block.model_dump()))
            # other block types (server tools etc.) are not used here
        return LLMResponse(
            content=content,
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=message.stop_reason or "end_turn",
        )

    def _request_kwargs(
        self, system: str, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self._settings.llm_model,
            "max_tokens": self._settings.llm_max_tokens,
            # stable prefix (tools render before system) → cacheable
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "thinking": {"type": "adaptive"},
            "tools": tools,
            "messages": self._to_params(messages),
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
            response = await self._client.messages.create(
                **self._request_kwargs(system, messages, tools)
            )
        except Exception as exc:
            raise _translate_error(exc) from exc
        return self._to_response(response)

    async def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]:
        try:
            async with self._client.messages.stream(
                **self._request_kwargs(system, messages, tools)
            ) as stream:
                async for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                    ):
                        yield TextDelta(text=event.delta.text)
                final = await stream.get_final_message()
        except Exception as exc:
            raise _translate_error(exc) from exc
        yield ResponseEnd(response=self._to_response(final))
