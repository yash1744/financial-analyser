import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SyncStatus, str_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.plaid_item import PlaidItem


class PlaidSyncState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Cursor position for Plaid /transactions/sync — one row per item."""

    __tablename__ = "plaid_sync_state"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one sync state per item; also serves as the FK index
    )
    # NULL until the first sync completes; Plaid returns the next cursor
    cursor: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    sync_status: Mapped[SyncStatus] = mapped_column(
        str_enum(SyncStatus),
        nullable=False,
        default=SyncStatus.IDLE,
    )

    plaid_item: Mapped["PlaidItem"] = relationship(back_populates="sync_state")
