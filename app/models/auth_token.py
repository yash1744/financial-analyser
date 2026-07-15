import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import TokenPurpose, str_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AuthToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Single-use, expiring token for email verification / password reset.

    Only the SHA-256 hash of the token is stored; the raw value exists
    solely in the link emailed to the user, so a database leak exposes
    nothing usable.
    """

    __tablename__ = "auth_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(str_enum(TokenPurpose), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
