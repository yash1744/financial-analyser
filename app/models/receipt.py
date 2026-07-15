import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class Receipt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-entered receipt details for one transaction (at most one per
    transaction); the uploaded images hang off receipt_images."""

    __tablename__ = "receipts"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    merchant_name: Mapped[str | None] = mapped_column(String(255))
    receipt_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    tip_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    comments: Mapped[str | None] = mapped_column(Text)

    transaction: Mapped["Transaction"] = relationship()
    images: Mapped[list["ReceiptImage"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptImage.created_at",
    )


class ReceiptImage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One uploaded receipt image; the bytes live in object storage under
    storage_key, the row holds the metadata."""

    __tablename__ = "receipt_images"

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    receipt: Mapped[Receipt] = relationship(back_populates="images")
