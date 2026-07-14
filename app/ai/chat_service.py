"""ChatService: persistence + orchestration around FinanceAgent.

Owns everything the agent shouldn't: loading/creating conversations,
replaying history, storing the run's messages, and committing. The route
stays thin; the agent stays persistence-free.
"""

import uuid
from collections.abc import AsyncIterator

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import AgentRunResult, FinanceAgent
from app.ai.llm_client import LLMClient
from app.ai.schemas import (
    AgentEvent,
    Block,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DoneEvent,
    TextBlock,
    ToolCallSummary,
)
from app.ai.tool_registry import ToolRegistry
from app.llm.tools import build_finance_toolset
from app.models.conversation import Conversation
from app.models.enums import MessageRole
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.services.exceptions import NotFoundError

# How many stored turns are replayed as LLM context. Only user/assistant
# text is replayed — tool results are point-in-time data that goes stale.
_HISTORY_LIMIT = 30

_blocks_adapter = TypeAdapter(list[Block])


class ChatService:
    def __init__(self, session: AsyncSession, llm: LLMClient) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.conversations = ConversationRepository(session)
        self.llm = llm

    def _build_agent(self, user_id: uuid.UUID) -> FinanceAgent:
        toolset = build_finance_toolset(self.session, user_id)
        return FinanceAgent(llm=self.llm, tools=ToolRegistry(toolset))

    async def chat(self, request: ChatRequest) -> ChatResponse:
        conversation, history = await self._prepare(request)
        agent = self._build_agent(request.user_id)
        result = await agent.run(history, request.message)
        await self._persist(conversation, result)
        return ChatResponse(
            conversation_id=conversation.id,
            message=result.text,
            tool_calls=_summaries(result),
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[AgentEvent]:
        """Yields token/tool events live, then a final done event (after
        the run has been persisted)."""
        conversation, history = await self._prepare(request)
        agent = self._build_agent(request.user_id)
        async for item in agent.run_stream(history, request.message):
            if isinstance(item, AgentRunResult):
                await self._persist(conversation, item)
                yield DoneEvent(
                    conversation_id=conversation.id,
                    message=item.text,
                    tool_calls=item.tool_events,
                )
            else:
                yield item

    # --- internals ---

    async def _prepare(
        self, request: ChatRequest
    ) -> tuple[Conversation, list[ChatMessage]]:
        if await self.users.get(request.user_id) is None:
            raise NotFoundError(f"user {request.user_id} does not exist")

        if request.conversation_id is None:
            conversation = await self.conversations.create(request.user_id)
            return conversation, []

        conversation = await self.conversations.get_for_user(
            request.conversation_id, request.user_id
        )
        if conversation is None:
            raise NotFoundError(
                f"conversation {request.conversation_id} does not exist"
            )
        return conversation, await self._history(conversation.id)

    async def _history(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        stored = await self.conversations.list_messages(conversation_id)
        history: list[ChatMessage] = []
        for message in stored:
            if message.role == MessageRole.TOOL:
                continue  # audit-only; not replayed
            blocks = _blocks_adapter.validate_python(message.content)
            text = "".join(b.text for b in blocks if isinstance(b, TextBlock))
            if text.strip():
                history.append(ChatMessage.text(message.role.value, text))
        return history[-_HISTORY_LIMIT:]

    async def _persist(
        self, conversation: Conversation, result: AgentRunResult
    ) -> None:
        for message in result.new_messages:
            self.conversations.add_message(
                conversation.id,
                MessageRole(message.role),
                [block.model_dump(mode="json") for block in message.content],
            )
        await self.conversations.touch(conversation.id)
        await self.session.commit()


def _summaries(result: AgentRunResult) -> list[ToolCallSummary]:
    return [
        ToolCallSummary(name=e.name, status=e.status, duration_ms=e.duration_ms)  # type: ignore[arg-type]
        for e in result.tool_events
    ]
