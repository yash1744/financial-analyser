import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MessageRole, str_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One turn in a conversation.

    content is JSONB holding provider-neutral blocks:
      user/assistant: [{"type": "text", "text": ...}, {"type": "tool_use", ...}]
      tool:           [{"type": "tool_result", ...}]
    Tool turns are stored for audit; only user/assistant text is replayed
    as LLM context (tool results are point-in-time and would go stale).
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(str_enum(MessageRole), nullable=False)
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
