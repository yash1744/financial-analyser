"""Finance-intelligence read service: answer-shaped compositions over
transaction history.

Sits beside AnalyticsService (chart-ready series) and the query services
(row retrieval); this layer composes aggregates and detects patterns,
returning structured DTOs. Every consumer — REST endpoints, LLM tools,
future scheduled jobs — calls these methods, so the logic exists once.
Read-only: never calls Plaid, never commits.
"""

import statistics
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics import AnalyticsRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.user import UserRepository
from app.schemas.insights import (
    Cadence,
    CategoryChange,
    CompareSpendingParams,
    CompareSpendingResponse,
    PeriodTotals,
    RecurringTransactionItem,
    RecurringTransactionsParams,
    RecurringTransactionsResponse,
    SpendingSummaryParams,
    SpendingSummaryResponse,
    TopEntry,
)
from app.services.exceptions import NotFoundError

_CENT = Decimal("0.01")

# Cadence bands: median gap between charges (days) → label. Bands are
# deliberately loose — real subscriptions drift around weekends and
# month lengths.
_CADENCE_BANDS: list[tuple[int, int, Cadence]] = [
    (5, 9, "weekly"),
    (12, 17, "biweekly"),
    (26, 35, "monthly"),
    (80, 100, "quarterly"),
    (350, 380, "yearly"),
]
# A merchant only counts as recurring when its gaps stay near the median
# and its amounts stay near the median amount.
_GAP_TOLERANCE_DAYS = 4
_AMOUNT_TOLERANCE = Decimal("0.20")  # ±20% of the median amount


def _money(value: Decimal | None) -> Decimal:
    return (value or Decimal("0")).quantize(_CENT)


def _pct_change(baseline: Decimal, comparison: Decimal) -> float | None:
    if not baseline:
        return None
    return round(float((comparison - baseline) / baseline * 100), 2)


class InsightsService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.analytics = AnalyticsRepository(session)
        self.transactions = TransactionRepository(session)

    async def _require_user(self, user_id: uuid.UUID) -> None:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")

    async def get_spending_summary(
        self, user_id: uuid.UUID, params: SpendingSummaryParams
    ) -> SpendingSummaryResponse:
        """Headline totals for a period plus its top category and merchant."""
        await self._require_user(user_id)
        totals = await self.analytics.period_totals(
            user_id, params.start_date, params.end_date, params.account_id
        )
        spending = _money(totals.spending)

        # Resolved bounds: requested dates win; otherwise what the data spans
        start = params.start_date or totals.first_date
        end = params.end_date or totals.last_date
        days = (end - start).days + 1 if start and end else None

        top_category = top_merchant = None
        if totals.transaction_count:
            categories = await self.analytics.category_totals(
                user_id, params.start_date, params.end_date, params.account_id
            )
            if categories:
                top = categories[0]
                top_category = TopEntry(
                    name=top.category_name or "Uncategorized", total=_money(top.total)
                )
            merchants = await self.analytics.merchant_totals(
                user_id,
                params.start_date,
                params.end_date,
                limit=1,
                account_id=params.account_id,
            )
            if merchants:
                top_merchant = TopEntry(
                    name=merchants[0].merchant_name, total=_money(merchants[0].total)
                )

        return SpendingSummaryResponse(
            start_date=start,
            end_date=end,
            total_spending=spending,
            total_income=_money(totals.income),
            net=_money(totals.spending - totals.income),
            transaction_count=totals.transaction_count,
            average_transaction=(
                _money(spending / totals.spending_transaction_count)
                if totals.spending_transaction_count
                else None
            ),
            daily_average_spending=_money(spending / days) if days else None,
            top_category=top_category,
            top_merchant=top_merchant,
        )

    async def compare_spending(
        self, user_id: uuid.UUID, params: CompareSpendingParams
    ) -> CompareSpendingResponse:
        """Baseline vs comparison period, with per-category deltas."""
        await self._require_user(user_id)

        if params.baseline_start is None:
            # Default: previous full month vs current month to date
            today = date.today()
            comparison_start = today.replace(day=1)
            comparison_end = today
            baseline_end = comparison_start - timedelta(days=1)
            baseline_start = baseline_end.replace(day=1)
        else:
            # The validator guarantees all four are present together
            baseline_start, baseline_end = params.baseline_start, params.baseline_end
            comparison_start, comparison_end = (
                params.comparison_start,
                params.comparison_end,
            )
        assert baseline_end and comparison_start and comparison_end

        baseline = await self._period(user_id, baseline_start, baseline_end)
        comparison = await self._period(user_id, comparison_start, comparison_end)

        base_categories = {
            (row.category_name or "Uncategorized"): _money(row.total)
            for row in await self.analytics.category_totals(
                user_id, baseline_start, baseline_end
            )
        }
        comp_categories = {
            (row.category_name or "Uncategorized"): _money(row.total)
            for row in await self.analytics.category_totals(
                user_id, comparison_start, comparison_end
            )
        }
        changes = [
            CategoryChange(
                category_name=name,
                baseline_total=(base := base_categories.get(name, Decimal("0"))),
                comparison_total=(comp := comp_categories.get(name, Decimal("0"))),
                change=_money(comp - base),
                change_pct=_pct_change(base, comp),
            )
            for name in sorted(base_categories.keys() | comp_categories.keys())
        ]
        changes.sort(key=lambda c: abs(c.change), reverse=True)

        return CompareSpendingResponse(
            baseline=baseline,
            comparison=comparison,
            spending_change=_money(comparison.total_spending - baseline.total_spending),
            spending_change_pct=_pct_change(
                baseline.total_spending, comparison.total_spending
            ),
            category_changes=changes,
        )

    async def _period(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> PeriodTotals:
        totals = await self.analytics.period_totals(user_id, start, end)
        return PeriodTotals(
            start_date=start,
            end_date=end,
            total_spending=_money(totals.spending),
            total_income=_money(totals.income),
            net=_money(totals.spending - totals.income),
            transaction_count=totals.transaction_count,
        )

    async def get_recurring_transactions(
        self, user_id: uuid.UUID, params: RecurringTransactionsParams
    ) -> RecurringTransactionsResponse:
        """Detect subscription-like charges: same merchant, steady amount,
        steady cadence."""
        await self._require_user(user_id)
        window_end = date.today()
        window_start = window_end - timedelta(days=params.lookback_days)
        rows = await self.transactions.recurring_candidates(
            user_id, window_start, params.min_occurrences
        )

        by_merchant: dict[str, list] = {}
        for row in rows:
            by_merchant.setdefault(row.merchant_name, []).append(row)

        items = [
            item
            for merchant_rows in by_merchant.values()
            if (item := _detect_pattern(merchant_rows, params.min_occurrences))
        ]
        items.sort(key=lambda i: i.average_amount, reverse=True)
        return RecurringTransactionsResponse(
            window_start=window_start, window_end=window_end, items=items
        )


def _detect_pattern(rows: list, min_occurrences: int) -> RecurringTransactionItem | None:
    """Classify one merchant's charges as recurring, or None.

    Requires: enough distinct charge dates, every gap between consecutive
    charges within _GAP_TOLERANCE_DAYS of the median gap, the median gap
    inside a known cadence band, and every amount within ±20% of the
    median amount.
    """
    # Same-day duplicates (e.g. split charges) collapse to one occurrence
    dates = sorted({row.transaction_date for row in rows})
    if len(dates) < min_occurrences:
        return None

    gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
    median_gap = statistics.median(gaps)
    if any(abs(gap - median_gap) > _GAP_TOLERANCE_DAYS for gap in gaps):
        return None
    cadence = next(
        (label for low, high, label in _CADENCE_BANDS if low <= median_gap <= high),
        None,
    )
    if cadence is None:
        return None

    amounts = sorted(row.amount for row in rows)
    median_amount = amounts[len(amounts) // 2]
    tolerance = median_amount * _AMOUNT_TOLERANCE
    if any(abs(amount - median_amount) > tolerance for amount in amounts):
        return None

    average = _money(sum(amounts, Decimal("0")) / len(amounts))
    return RecurringTransactionItem(
        merchant_name=rows[0].merchant_name,
        cadence=cadence,
        average_amount=average,
        currency=rows[-1].currency,
        occurrence_count=len(dates),
        first_date=dates[0],
        last_date=dates[-1],
        next_expected_date=dates[-1] + timedelta(days=round(median_gap)),
    )
