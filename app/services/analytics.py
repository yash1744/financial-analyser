"""Analytics read services: aggregate SQL results → response DTOs.

The repository returns SQL aggregates; this layer adds derived values
(net, shares, month-over-month deltas, zero-filled month sequences) and
normalizes money to 2 decimal places.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics import AnalyticsRepository
from app.repositories.user import UserRepository
from app.schemas.analytics import (
    CategoryBreakdownItem,
    CategoryBreakdownResponse,
    MonthlySpendingPoint,
    MonthlySpendingResponse,
    MonthOverMonthPoint,
    MonthOverMonthResponse,
    TopMerchantItem,
    TopMerchantsResponse,
)
from app.services.exceptions import NotFoundError

_CENT = Decimal("0.01")


def _money(value: Decimal | None) -> Decimal:
    return (value or Decimal("0")).quantize(_CENT)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _shift_month(anchor: date, delta: int) -> date:
    total = anchor.year * 12 + (anchor.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.analytics = AnalyticsRepository(session)

    async def _require_user(self, user_id: uuid.UUID) -> None:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")

    async def monthly_spending(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        account_id: uuid.UUID | None = None,
    ) -> MonthlySpendingResponse:
        await self._require_user(user_id)
        rows = await self.analytics.monthly_totals(user_id, start_date, end_date, account_id)
        return MonthlySpendingResponse(
            months=[
                MonthlySpendingPoint(
                    month=_month_key(row.month),
                    spending=_money(row.spending),
                    income=_money(row.income),
                    net=_money(row.spending - row.income),
                    transaction_count=row.transaction_count,
                )
                for row in rows
            ]
        )

    async def category_breakdown(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        account_id: uuid.UUID | None = None,
    ) -> CategoryBreakdownResponse:
        await self._require_user(user_id)
        rows = await self.analytics.category_totals(
            user_id, start_date, end_date, account_id
        )
        total_spending = sum((row.total for row in rows), Decimal("0"))
        return CategoryBreakdownResponse(
            total_spending=_money(total_spending),
            categories=[
                CategoryBreakdownItem(
                    category_id=row.category_id,
                    category_name=row.category_name or "Uncategorized",
                    is_custom=row.is_custom,
                    total=_money(row.total),
                    transaction_count=row.transaction_count,
                    share_pct=(
                        round(float(row.total / total_spending * 100), 2)
                        if total_spending
                        else 0.0
                    ),
                )
                for row in rows
            ],
        )

    async def top_merchants(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 10,
    ) -> TopMerchantsResponse:
        await self._require_user(user_id)
        rows = await self.analytics.merchant_totals(user_id, start_date, end_date, limit)
        return TopMerchantsResponse(
            merchants=[
                TopMerchantItem(
                    merchant_name=row.merchant_name,
                    total=_money(row.total),
                    transaction_count=row.transaction_count,
                )
                for row in rows
            ]
        )

    async def month_over_month(
        self, user_id: uuid.UUID, months: int = 6
    ) -> MonthOverMonthResponse:
        """Spending for the last `months` calendar months (zero-filled),
        each with its change vs the previous month."""
        await self._require_user(user_id)
        current_month = date.today().replace(day=1)
        window_start = _shift_month(current_month, -(months - 1))
        rows = await self.analytics.monthly_totals(user_id, start_date=window_start)
        spending_by_month = {_month_key(row.month): row.spending for row in rows}

        points: list[MonthOverMonthPoint] = []
        previous: Decimal | None = None
        for offset in range(months):
            key = _month_key(_shift_month(window_start, offset))
            spending = _money(spending_by_month.get(key))
            change = None if previous is None else _money(spending - previous)
            change_pct = (
                round(float((spending - previous) / previous * 100), 2)
                if previous  # None on first month, no % against a 0 baseline
                else None
            )
            points.append(
                MonthOverMonthPoint(
                    month=key, spending=spending, change=change, change_pct=change_pct
                )
            )
            previous = spending
        return MonthOverMonthResponse(months=points)
