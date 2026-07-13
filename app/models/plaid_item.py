import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PlaidItemStatus, str_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.plaid_sync_state import PlaidSyncState
    from app.models.user import User


class PlaidItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One connected institution login (a Plaid 'Item') for a user."""

    __tablename__ = "plaid_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plaid_item_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    institution_id: Mapped[str | None] = mapped_column(String(255))
    institution_name: Mapped[str | None] = mapped_column(String(255))
    # Ciphertext only — encryption/decryption happens in the service layer
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PlaidItemStatus] = mapped_column(
        str_enum(PlaidItemStatus),
        nullable=False,
        default=PlaidItemStatus.ACTIVE,
    )

    user: Mapped["User"] = relationship(back_populates="plaid_items")
    accounts: Mapped[list["Account"]] = relationship(
        back_populates="plaid_item",
        cascade="all, delete-orphan",
    )
    sync_state: Mapped["PlaidSyncState | None"] = relationship(
        back_populates="plaid_item",
        cascade="all, delete-orphan",
    )
