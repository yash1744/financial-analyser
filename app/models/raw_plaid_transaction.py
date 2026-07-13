import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ProcessingStatus, str_enum
from app.models.mixins import UUIDPrimaryKeyMixin


class RawPlaidTransaction(Base, UUIDPrimaryKeyMixin):
    """Immutable landing zone for Plaid API payloads.

    Kept verbatim for debugging, reprocessing, and training future
    categorization models. Rows are written once and marked processed;
    normalization into `transactions` happens asynchronously.
    """

    __tablename__ = "raw_plaid_transactions"
    __table_args__ = (
        # The worker's queue scan: only unprocessed rows, oldest first.
        # Partial index stays tiny no matter how large the table grows.
        Index(
            "ix_raw_plaid_transactions_pending",
            "received_at",
            postgresql_where=text("processing_status = 'pending'"),
        ),
    )

    plaid_transaction_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        str_enum(ProcessingStatus),
        nullable=False,
        default=ProcessingStatus.PENDING,
    )
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
