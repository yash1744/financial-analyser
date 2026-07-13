import uuid
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

# All spending figures are gross outflow (Plaid convention: amount > 0),
# income is gross inflow; net = spending - income.


class AnalyticsRangeQuery(BaseModel):
    user_id: uuid.UUID  # moves to the auth context once authentication lands
    start_date: date | None = None  # inclusive
    end_date: date | None = None  # inclusive

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class MonthlySpendingQuery(AnalyticsRangeQuery):
    account_id: uuid.UUID | None = None


class CategoryBreakdownQuery(AnalyticsRangeQuery):
    account_id: uuid.UUID | None = None


class TopMerchantsQuery(AnalyticsRangeQuery):
    limit: int = Field(default=10, ge=1, le=50)


class MonthOverMonthQuery(BaseModel):
    user_id: uuid.UUID
    months: int = Field(default=6, ge=2, le=24)


class MonthlySpendingPoint(BaseModel):
    month: str  # "YYYY-MM"
    spending: Decimal
    income: Decimal
    net: Decimal
    transaction_count: int


class MonthlySpendingResponse(BaseModel):
    months: list[MonthlySpendingPoint]


class CategoryBreakdownItem(BaseModel):
    category_id: uuid.UUID | None
    category_name: str  # "Uncategorized" when category_id is null
    total: Decimal
    transaction_count: int
    share_pct: float  # of total spending in the range, 0–100


class CategoryBreakdownResponse(BaseModel):
    total_spending: Decimal
    categories: list[CategoryBreakdownItem]


class TopMerchantItem(BaseModel):
    merchant_name: str
    total: Decimal
    transaction_count: int


class TopMerchantsResponse(BaseModel):
    merchants: list[TopMerchantItem]


class MonthOverMonthPoint(BaseModel):
    month: str  # "YYYY-MM"
    spending: Decimal
    change: Decimal | None  # vs previous month; None for the first month
    change_pct: float | None  # None when previous month spending was 0


class MonthOverMonthResponse(BaseModel):
    months: list[MonthOverMonthPoint]
