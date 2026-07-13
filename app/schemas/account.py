import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plaid_account_id: str
    name: str
    account_type: str
    account_subtype: str | None
    current_balance: Decimal | None
    available_balance: Decimal | None
    currency: str


class AccountsSyncRequest(BaseModel):
    # user_id moves to the auth context once authentication lands
    user_id: uuid.UUID
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
