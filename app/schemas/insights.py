"""Finance-intelligence contracts.

The *Params models deliberately exclude user_id: they are shared between
REST query models (which inherit them and add user_id) and LLM tool input
schemas (where user_id is injected by the toolset, never chosen by the
model). Keep them flat and JSON-schema-friendly — they double as tool
definitions.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


def _validate_range(start: date | None, end: date | None, label: str) -> None:
    if start and end and start > end:
        raise ValueError(f"{label} start date must be on or before its end date")


# --- spending summary ---


class SpendingSummaryParams(BaseModel):
    start_date: date | None = Field(
        default=None, description="Inclusive range start; omit for all history"
    )
    end_date: date | None = Field(
        default=None, description="Inclusive range end; omit for all history"
    )
    account_id: uuid.UUID | None = Field(
        default=None, description="Restrict to one account; omit for all accounts"
    )

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        _validate_range(self.start_date, self.end_date, "range")
        return self


class SpendingSummaryQuery(SpendingSummaryParams):
    user_id: uuid.UUID  # moves to the auth context once authentication lands


class TopEntry(BaseModel):
    name: str
    total: Decimal


class SpendingSummaryResponse(BaseModel):
    # Resolved bounds: the requested dates, falling back to the first/last
    # transaction actually found (null when the range holds no transactions).
    start_date: date | None
    end_date: date | None
    total_spending: Decimal
    total_income: Decimal
    net: Decimal  # spending − income (Plaid convention: positive = outflow)
    transaction_count: int
    average_transaction: Decimal | None  # mean outflow transaction
    daily_average_spending: Decimal | None  # spending / days in resolved range
    top_category: TopEntry | None
    top_merchant: TopEntry | None


# --- compare spending ---


class CompareSpendingParams(BaseModel):
    """Compare a baseline period against a comparison period.

    Give all four dates, or none: the default compares the previous full
    calendar month (baseline) against the current month to date.
    """

    baseline_start: date | None = None
    baseline_end: date | None = None
    comparison_start: date | None = None
    comparison_end: date | None = None

    @model_validator(mode="after")
    def validate_periods(self) -> Self:
        given = [
            self.baseline_start,
            self.baseline_end,
            self.comparison_start,
            self.comparison_end,
        ]
        if any(v is not None for v in given) and any(v is None for v in given):
            raise ValueError("provide all four period dates, or none for the default")
        _validate_range(self.baseline_start, self.baseline_end, "baseline")
        _validate_range(self.comparison_start, self.comparison_end, "comparison")
        return self


class CompareSpendingQuery(CompareSpendingParams):
    user_id: uuid.UUID


class PeriodTotals(BaseModel):
    start_date: date
    end_date: date
    total_spending: Decimal
    total_income: Decimal
    net: Decimal
    transaction_count: int


class CategoryChange(BaseModel):
    category_name: str  # "Uncategorized" when the category is null
    baseline_total: Decimal
    comparison_total: Decimal
    change: Decimal  # comparison − baseline
    change_pct: float | None  # None when baseline is 0


class CompareSpendingResponse(BaseModel):
    baseline: PeriodTotals
    comparison: PeriodTotals
    spending_change: Decimal
    spending_change_pct: float | None
    category_changes: list[CategoryChange]  # sorted by |change|, largest first


# --- recurring transactions ---


class RecurringTransactionsParams(BaseModel):
    lookback_days: int = Field(
        default=180, ge=60, le=730, description="History window to analyze"
    )
    min_occurrences: int = Field(
        default=3, ge=2, le=12, description="Minimum charges to call a pattern"
    )


class RecurringTransactionsQuery(RecurringTransactionsParams):
    user_id: uuid.UUID


Cadence = Literal["weekly", "biweekly", "monthly", "quarterly", "yearly"]


class RecurringTransactionItem(BaseModel):
    merchant_name: str
    cadence: Cadence
    average_amount: Decimal
    currency: str
    occurrence_count: int
    first_date: date
    last_date: date
    next_expected_date: date


class RecurringTransactionsResponse(BaseModel):
    window_start: date
    window_end: date
    items: list[RecurringTransactionItem]  # sorted by average_amount, largest first
