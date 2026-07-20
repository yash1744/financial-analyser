import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class UserCategory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's own grouping bucket — private, flat, unrelated to the
    global Plaid-derived Category taxonomy except via CategoryMapping."""

    __tablename__ = "user_categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class CategoryMapping(Base):
    """Rolls up one Plaid category into one of a user's own categories.

    PK is (user_id, category_id): a given Plaid category maps to at most
    one user category per user — a strict partition, not an overlapping
    grouping, so analytics rollups never double-count a transaction.
    """

    __tablename__ = "category_mappings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
