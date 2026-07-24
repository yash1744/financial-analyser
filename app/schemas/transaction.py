import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TransactionClassification, TransactionType
from app.schemas.label import LabelResponse


class TransactionsSyncApiRequest(BaseModel):
    # Sync one connected item, or every item the user has when omitted
    item_id: uuid.UUID | None = None


class ItemTransactionsSyncSummary(BaseModel):
    item_id: uuid.UUID
    plaid_item_id: str
    institution_name: str | None
    added: int
    modified: int
    removed: int
    skipped: int
    next_cursor: str
    last_synced_at: datetime


class TransactionsSyncApiResponse(BaseModel):
    items: list[ItemTransactionsSyncSummary]


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    plaid_transaction_id: str
    transaction_date: date
    merchant_name: str | None
    amount: Decimal
    currency: str
    category_id: uuid.UUID | None
    transaction_type: TransactionType
    classification: TransactionClassification
    pending: bool
    created_at: datetime
    labels: list[LabelResponse]


class TransactionSearchParams(BaseModel):
    """Search filters without user_id — shared by the REST query model
    (which adds user_id) and the LLM tool schema (which injects it)."""

    account_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Match transactions in any one of these accounts",
    )
    category_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Match transactions in any one of these categories",
    )
    classifications: list[TransactionClassification] | None = Field(
        default=None,
        description="Match transactions with any one of these classifications",
    )
    merchant: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Case-insensitive substring match on the merchant name",
    )
    label_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Match transactions carrying any one of these labels",
    )
    start_date: date | None = None  # inclusive
    end_date: date | None = None  # inclusive
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    sort_by: Literal["transaction_date", "amount", "merchant_name"] = "transaction_date"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError("min_amount must be less than or equal to max_amount")
        return self


class TransactionListQuery(TransactionSearchParams):
    """GET /transactions query parameters (the user comes from auth)."""


class PaginatedTransactionsResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    total_amount: Decimal
    page: int
    page_size: int
    total_pages: int
