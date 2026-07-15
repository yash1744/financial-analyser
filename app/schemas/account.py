import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plaid_account_id: str
    # `name` is always Plaid's original; `nickname` is the user override;
    # `display_name` is what the UI should render (nickname or name)
    name: str
    nickname: str | None
    display_name: str
    account_type: str
    account_subtype: str | None
    current_balance: Decimal | None
    available_balance: Decimal | None
    currency: str


class AccountNicknameUpdate(BaseModel):
    """Set or clear an account nickname. null / omitted clears it, reverting
    the display to the original Plaid name."""

    nickname: str | None = Field(default=None, max_length=100)

    @field_validator("nickname")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None  # blank/whitespace-only clears the nickname


class AccountsSyncRequest(BaseModel):
    # Sync one connected item, or every item the user has when omitted
    item_id: uuid.UUID | None = None


class ItemAccountsSyncSummary(BaseModel):
    item_id: uuid.UUID
    plaid_item_id: str
    institution_name: str | None
    created: int
    updated: int
    skipped: int
    accounts: list[AccountResponse]


class AccountsSyncResponse(BaseModel):
    items: list[ItemAccountsSyncSummary]
