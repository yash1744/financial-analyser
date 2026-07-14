import uuid
from typing import Any

from sqlalchemy import func, select, update

from app.models.conversation import Conversation
from app.models.enums import MessageRole
from app.models.message import Message
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    async def get_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        """Ownership is part of the lookup — one user can never load
        another's conversation."""
        return await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

    async def create(self, user_id: uuid.UUID) -> Conversation:
        conversation = Conversation(user_id=user_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def list_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.scalars())

    def add_message(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: list[dict[str, Any]],
    ) -> Message:
        message = Message(
            conversation_id=conversation_id, role=role, content=content
        )
        self.session.add(message)
        return message

    async def touch(self, conversation_id: uuid.UUID) -> None:
        """Bump updated_at when messages are appended (the row itself
        doesn't change, so onupdate never fires)."""
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )
