"""Provider-neutral message/event types plus the /ai/chat API contracts.

The block types mirror the least common denominator of tool-using chat
APIs: a message is a role plus a list of blocks. Only the concrete
LLMClient implementation knows how these map onto a provider's wire
format.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# --- conversation blocks (stored in messages.content as JSONB) ---


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str  # provider-assigned call id, echoed back in the result
    name: str
    input: dict[str, Any]


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str  # JSON-serialized tool output or error text
    is_error: bool = False


class ThinkingBlock(BaseModel):
    """Opaque provider reasoning block. Echoed back verbatim when the
    conversation continues on the same model (required by the provider);
    other models ignore it. Never rendered to users."""

    type: Literal["thinking"] = "thinking"
    raw: dict[str, Any]


Block = Annotated[
    TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock,
    Field(discriminator="type"),
]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: list[Block]

    @classmethod
    def text(
        cls, role: Literal["user", "assistant"], text: str
    ) -> "ChatMessage":
        return cls(role=role, content=[TextBlock(text=text)])


# --- LLM client results ---


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    content: list[Block]  # full assistant turn, replayable as-is
    text: str  # concatenated text blocks (may be empty on pure tool turns)
    tool_calls: list[ToolCall]
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | "refusal" | ...


class TextDelta(BaseModel):
    """Streaming: an incremental piece of assistant text."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class ResponseEnd(BaseModel):
    """Streaming: the turn finished; carries the accumulated response."""

    type: Literal["response_end"] = "response_end"
    response: LLMResponse


LLMStreamEvent = TextDelta | ResponseEnd


# --- agent events (streamed) ---


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ToolEvent(BaseModel):
    type: Literal["tool"] = "tool"
    name: str
    status: Literal["running", "completed", "failed"]
    duration_ms: int | None = None  # set on completed/failed, absent on running


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    conversation_id: uuid.UUID | None = None
    message: str
    tool_calls: list[ToolEvent]


AgentEvent = TokenEvent | ToolEvent | DoneEvent


# --- /ai/chat API contracts ---


class ChatRequest(BaseModel):
    # the acting user comes from the auth context, never from the body
    conversation_id: uuid.UUID | None = None  # omit to start a new conversation
    message: str = Field(min_length=1, max_length=4000)


class ToolCallSummary(BaseModel):
    name: str
    status: Literal["completed", "failed"]
    duration_ms: int | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: str
    tool_calls: list[ToolCallSummary]


class ConversationSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
