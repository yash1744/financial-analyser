import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class Category(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "categories"
    __table_args__ = (
        # One name per parent; NULLS NOT DISTINCT (PG15+) also blocks
        # duplicate top-level names, where parent is NULL
        UniqueConstraint(
            "parent_category_id", "name", postgresql_nulls_not_distinct=True
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    parent: Mapped["Category | None"] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
