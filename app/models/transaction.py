import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TransactionType, str_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.category import Category


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Normalized transaction; raw Plaid payloads live in raw_plaid_transactions."""

    __tablename__ = "transactions"
    __table_args__ = (
        # The hot path for both the UI and analytics: one account's
        # history, newest first
        Index(
            "ix_transactions_account_id_transaction_date",
            "account_id",
            "transaction_date",
            postgresql_using="btree",
            postgresql_ops={"transaction_date": "DESC"},
        ),
        # Cross-account queries by date (monthly summaries, trends)
        Index("ix_transactions_transaction_date", "transaction_date"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Dedupe guard: Plaid's ID is globally unique; upserts key on this
    plaid_transaction_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(255), index=True)
    # Sign convention: positive = money out (Plaid's convention), kept
    # as-is so raw and normalized rows agree
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'USD'"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        index=True,
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        str_enum(TransactionType),
        nullable=False,
    )
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    account: Mapped["Account"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
