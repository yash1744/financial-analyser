import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ReceiptDetailsUpdate(BaseModel):
    """Full replacement of the user-entered receipt details (PUT
    semantics): omitted/null fields clear the stored value."""

    merchant_name: str | None = Field(default=None, max_length=255)
    receipt_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    tax_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999"))
    tip_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999"))
    comments: str | None = Field(default=None, max_length=2000)


class ReceiptImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    merchant_name: str | None
    receipt_date: date | None
    notes: str | None
    tax_amount: Decimal | None
    tip_amount: Decimal | None
    comments: str | None
    images: list[ReceiptImageResponse]
    created_at: datetime
    updated_at: datetime
