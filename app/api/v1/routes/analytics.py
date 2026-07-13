from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AnalyticsServiceDep
from app.schemas.analytics import (
    CategoryBreakdownQuery,
    CategoryBreakdownResponse,
    MonthlySpendingQuery,
    MonthlySpendingResponse,
    MonthOverMonthQuery,
    MonthOverMonthResponse,
    TopMerchantsQuery,
    TopMerchantsResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/monthly-spending", response_model=MonthlySpendingResponse)
async def monthly_spending(
    query: Annotated[MonthlySpendingQuery, Query()], service: AnalyticsServiceDep
) -> MonthlySpendingResponse:
    """Spending / income / net per calendar month."""
    return await service.monthly_spending(
        query.user_id, query.start_date, query.end_date, query.account_id
    )


@router.get("/category-breakdown", response_model=CategoryBreakdownResponse)
async def category_breakdown(
    query: Annotated[CategoryBreakdownQuery, Query()], service: AnalyticsServiceDep
) -> CategoryBreakdownResponse:
    """Spending by category with each category's share of the total."""
    return await service.category_breakdown(
        query.user_id, query.start_date, query.end_date, query.account_id
    )


@router.get("/top-merchants", response_model=TopMerchantsResponse)
async def top_merchants(
    query: Annotated[TopMerchantsQuery, Query()], service: AnalyticsServiceDep
) -> TopMerchantsResponse:
    """Merchants ranked by total spending."""
    return await service.top_merchants(
        query.user_id, query.start_date, query.end_date, query.limit
    )


@router.get("/month-over-month", response_model=MonthOverMonthResponse)
async def month_over_month(
    query: Annotated[MonthOverMonthQuery, Query()], service: AnalyticsServiceDep
) -> MonthOverMonthResponse:
    """Last N calendar months of spending with deltas vs the prior month."""
    return await service.month_over_month(query.user_id, query.months)
