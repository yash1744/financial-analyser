from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, InsightsServiceDep
from app.schemas.insights import (
    CompareSpendingParams,
    CompareSpendingResponse,
    RecurringTransactionsParams,
    RecurringTransactionsResponse,
    SpendingSummaryParams,
    SpendingSummaryResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/spending-summary", response_model=SpendingSummaryResponse)
async def spending_summary(
    query: Annotated[SpendingSummaryParams, Query()],
    user: CurrentUserDep,
    service: InsightsServiceDep,
) -> SpendingSummaryResponse:
    """Headline totals for a period plus its top category and merchant."""
    return await service.get_spending_summary(user.id, query)


@router.get("/compare-spending", response_model=CompareSpendingResponse)
async def compare_spending(
    query: Annotated[CompareSpendingParams, Query()],
    user: CurrentUserDep,
    service: InsightsServiceDep,
) -> CompareSpendingResponse:
    """Baseline vs comparison period with per-category deltas.

    Omit all dates to compare the previous full month against the current
    month to date."""
    return await service.compare_spending(user.id, query)


@router.get("/recurring-transactions", response_model=RecurringTransactionsResponse)
async def recurring_transactions(
    query: Annotated[RecurringTransactionsParams, Query()],
    user: CurrentUserDep,
    service: InsightsServiceDep,
) -> RecurringTransactionsResponse:
    """Subscription-like charges: same merchant, steady amount, steady cadence."""
    return await service.get_recurring_transactions(user.id, query)
