"""Typed results returned by PlaidService.

Transactions and accounts are kept as raw dicts on purpose: the raw
payload is stored verbatim in raw_plaid_transactions, and normalization
into app schemas is a separate concern.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PlaidItemStatus


class LinkTokenResult(BaseModel):
    link_token: str
    expiration: datetime


class ExchangedPublicToken(BaseModel):
    access_token: str
    item_id: str


class AccountsSnapshot(BaseModel):
    accounts: list[dict[str, Any]]
    item: dict[str, Any]


class TransactionsSyncResult(BaseModel):
    added: list[dict[str, Any]]
    modified: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    next_cursor: str


# --- API request/response contracts ---
# user_id in request bodies is a stand-in until authentication exists;
# it will move to the auth context then.


class LinkTokenRequest(BaseModel):
    user_id: uuid.UUID


class LinkTokenResponse(BaseModel):
    link_token: str
    expiration: datetime


class ExchangeTokenRequest(BaseModel):
    user_id: uuid.UUID
    public_token: str = Field(min_length=1, max_length=500)


class PlaidItemResponse(BaseModel):
    """A connected institution. Never exposes the access token."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plaid_item_id: str
    institution_id: str | None
    institution_name: str | None
    status: PlaidItemStatus
    created_at: datetime
