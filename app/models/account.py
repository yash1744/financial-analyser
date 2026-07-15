import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.plaid_item import PlaidItem
    from app.models.transaction import Transaction


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A bank/credit account under a Plaid item (checking, savings, card…)."""

    __tablename__ = "accounts"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plaid_account_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # The name Plaid provides; refreshed on every sync
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # User-chosen display name; NULL means "fall back to the Plaid name".
    # Plaid syncs only touch `name`, so nicknames survive them.
    nickname: Mapped[str | None] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)  # depository, credit…
    account_subtype: Mapped[str | None] = mapped_column(String(50))  # checking, savings…
    current_balance: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    available_balance: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )

    @property
    def display_name(self) -> str:
        """What the UI should show: the nickname when set, else Plaid's name."""
        return self.nickname or self.name

    plaid_item: Mapped["PlaidItem"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
