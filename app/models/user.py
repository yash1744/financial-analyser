from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.plaid_item import PlaidItem


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    # Store emails lowercased at the service layer; unique index enforces it
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # bcrypt hash; NULL only on rows created before auth existed — those
    # accounts are permanently locked out (no login, no re-registration)
    password_hash: Mapped[str | None] = mapped_column(String(255))

    plaid_items: Mapped[list["PlaidItem"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
