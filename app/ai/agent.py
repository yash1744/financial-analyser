"""FinanceAgent: the conversation/tool loop.

Moves messages between the LLM and the tool registry until the model
answers in text. Contains no SQL, no business logic, and no financial
calculations — those live behind the tools.
"""

import logging
import time
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.ai.exceptions import AgentLoopError
from app.ai.llm_client import LLMClient
from app.ai.prompts import build_system_prompt
from app.ai.schemas import (
    ChatMessage,
    LLMResponse,
    ResponseEnd,
    TokenEvent,
    ToolCall,
    ToolEvent,
    ToolResultBlock,
)
from app.ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_REFUSAL_TEXT = "I can't help with that request."
_EMPTY_TEXT = "I wasn't able to produce an answer — please try rephrasing."


class AgentRunResult(BaseModel):
    """What one agent run produced: the final text, every message created
    during the run (for persistence), and a tool-call audit trail."""

    text: str
    new_messages: list[ChatMessage]
    tool_events: list[ToolEvent]


AgentStreamItem = TokenEvent | ToolEvent | AgentRunResult


class FinanceAgent:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        max_iterations: int = 8,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._max_iterations = max_iterations

    async def run(
        self, history: list[ChatMessage], user_message: str
    ) -> AgentRunResult:
        """Non-streaming loop: returns only the final result."""
        result: AgentRunResult | None = None
        async for item in self._loop(history, user_message, stream=False):
            if isinstance(item, AgentRunResult):
                result = item
        assert result is not None  # _loop always ends with a result or raises
        return result

    def run_stream(
        self, history: list[ChatMessage], user_message: str
    ) -> AsyncIterator[AgentStreamItem]:
        """Streaming loop: yields TokenEvent / ToolEvent as they happen,
        then the AgentRunResult as the final item."""
        return self._loop(history, user_message, stream=True)

    async def _loop(
        self, history: list[ChatMessage], user_message: str, stream: bool
    ) -> AsyncIterator[AgentStreamItem]:
        system = build_system_prompt()
        tools = self._tools.definitions()

        user_msg = ChatMessage.text("user", user_message)
        messages = [*history, user_msg]
        new_messages: list[ChatMessage] = [user_msg]
        tool_events: list[ToolEvent] = []
        final_text: str | None = None

        for _ in range(self._max_iterations):
            if stream:
                response: LLMResponse | None = None
                async for event in self._llm.stream(
                    system=system, messages=messages, tools=tools
                ):
                    if isinstance(event, ResponseEnd):
                        response = event.response
                    elif event.text:
                        yield TokenEvent(text=event.text)
                assert response is not None  # stream always ends with ResponseEnd
            else:
                response = await self._llm.complete(
                    system=system, messages=messages, tools=tools
                )

            assistant = ChatMessage(role="assistant", content=response.content)
            messages.append(assistant)
            new_messages.append(assistant)

            if not response.tool_calls:
                if response.stop_reason == "refusal":
                    final_text = response.text or _REFUSAL_TEXT
                else:
                    final_text = response.text or _EMPTY_TEXT
                break

            # Execute every call from this turn; all results go back in
            # one message (splitting them degrades parallel tool use).
            result_blocks: list[ToolResultBlock] = []
            for call in response.tool_calls:
                running = ToolEvent(name=call.name, status="running")
                if stream:
                    yield running
                started = time.perf_counter()
                execution = await self._execute(call)
                done = ToolEvent(
                    name=call.name,
                    status="failed" if execution.is_error else "completed",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                tool_events.append(done)
                if stream:
                    yield done
                result_blocks.append(
                    ToolResultBlock(
                        tool_use_id=call.id,
                        content=execution.content,
                        is_error=execution.is_error,
                    )
                )
            tool_msg = ChatMessage(role="tool", content=result_blocks)
            messages.append(tool_msg)
            new_messages.append(tool_msg)

        if final_text is None:
            raise AgentLoopError(
                f"no final answer after {self._max_iterations} tool iterations"
            )

        yield AgentRunResult(
            text=final_text, new_messages=new_messages, tool_events=tool_events
        )

    async def _execute(self, call: ToolCall):
        logger.info("tool call: %s", call.name)
        return await self._tools.execute(call.name, call.arguments)
