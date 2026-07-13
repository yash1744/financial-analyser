from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import InsightsServiceDep
from app.schemas.insights import (
    CompareSpendingQuery,
    CompareSpendingResponse,
    RecurringTransactionsQuery,
    RecurringTransactionsResponse,
    SpendingSummaryQuery,
    SpendingSummaryResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/spending-summary", response_model=SpendingSummaryResponse)
async def spending_summary(
    query: Annotated[SpendingSummaryQuery, Query()], service: InsightsServiceDep
) -> SpendingSummaryResponse:
    """Headline totals for a period plus its top category and merchant."""
    return await service.get_spending_summary(query.user_id, query)


@router.get("/compare-spending", response_model=CompareSpendingResponse)
async def compare_spending(
    query: Annotated[CompareSpendingQuery, Query()], service: InsightsServiceDep
) -> CompareSpendingResponse:
    """Baseline vs comparison period with per-category deltas.

    Omit all dates to compare the previous full month against the current
    month to date."""
    return await service.compare_spending(query.user_id, query)


@router.get("/recurring-transactions", response_model=RecurringTransactionsResponse)
async def recurring_transactions(
    query: Annotated[RecurringTransactionsQuery, Query()], service: InsightsServiceDep
) -> RecurringTransactionsResponse:
    """Subscription-like charges: same merchant, steady amount, steady cadence."""
    return await service.get_recurring_transactions(query.user_id, query)
