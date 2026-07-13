"""SQL aggregation over transactions. Rows in, aggregates out — Python
never loops over individual transactions.

Every query is scoped to a user via transactions → accounts → plaid_items;
that path is fully indexed (ix_plaid_items_user_id, ix_accounts_plaid_item_id,
ix_transactions_account_id_transaction_date), and date-range predicates ride
ix_transactions_transaction_date or the composite index.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, case, func, select

from app.models.account import Account
from app.models.category import Category
from app.models.plaid_item import PlaidItem
from app.models.transaction import Transaction
from app.repositories.base import BaseRepository

_ZERO = Decimal("0")

# Gross outflow / inflow per Plaid's sign convention (positive = money out)
_SPENDING = func.coalesce(
    func.sum(case((Transaction.amount > 0, Transaction.amount), else_=_ZERO)), _ZERO
)
_INCOME = func.coalesce(
    -func.sum(case((Transaction.amount < 0, Transaction.amount), else_=_ZERO)), _ZERO
)


class AnalyticsRepository(BaseRepository):
    def _scoped(
        self,
        query: Any,
        user_id: uuid.UUID,
        start_date: date | None,
        end_date: date | None,
        account_id: uuid.UUID | None = None,
    ) -> Any:
        query = (
            query.join(Account, Transaction.account_id == Account.id)
            .join(PlaidItem, Account.plaid_item_id == PlaidItem.id)
            .where(PlaidItem.user_id == user_id)
        )
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        if start_date is not None:
            query = query.where(Transaction.transaction_date >= start_date)
        if end_date is not None:
            query = query.where(Transaction.transaction_date <= end_date)
        return query

    async def monthly_totals(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[Row]:
        month = func.date_trunc("month", Transaction.transaction_date).label("month")
        query = self._scoped(
            select(
                month,
                _SPENDING.label("spending"),
                _INCOME.label("income"),
                func.count(Transaction.id).label("transaction_count"),
            ),
            user_id,
            start_date,
            end_date,
            account_id,
        ).group_by(month).order_by(month)
        return list(await self.session.execute(query))

    async def period_totals(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        account_id: uuid.UUID | None = None,
    ) -> Row:
        """One aggregate row for the whole period (always returned, possibly
        all-zero): spending, income, counts, actual first/last dates."""
        spending_count = func.coalesce(
            func.sum(case((Transaction.amount > 0, 1), else_=0)), 0
        )
        query = self._scoped(
            select(
                _SPENDING.label("spending"),
                _INCOME.label("income"),
                func.count(Transaction.id).label("transaction_count"),
                spending_count.label("spending_transaction_count"),
                func.min(Transaction.transaction_date).label("first_date"),
                func.max(Transaction.transaction_date).label("last_date"),
            ),
            user_id,
            start_date,
            end_date,
            account_id,
        )
        return (await self.session.execute(query)).one()

    async def category_totals(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[Row]:
        """Spending (outflow only) grouped by category; NULL = uncategorized."""
        total = func.sum(Transaction.amount).label("total")
        query = (
            self._scoped(
                select(
                    Transaction.category_id,
                    Category.name.label("category_name"),
                    total,
                    func.count(Transaction.id).label("transaction_count"),
                ),
                user_id,
                start_date,
                end_date,
                account_id,
            )
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(Transaction.amount > 0)
            .group_by(Transaction.category_id, Category.name)
            .order_by(total.desc())
        )
        return list(await self.session.execute(query))

    async def merchant_totals(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 10,
        account_id: uuid.UUID | None = None,
    ) -> list[Row]:
        """Top merchants by spending (outflow only, unnamed merchants excluded)."""
        total = func.sum(Transaction.amount).label("total")
        query = (
            self._scoped(
                select(
                    Transaction.merchant_name,
                    total,
                    func.count(Transaction.id).label("transaction_count"),
                ),
                user_id,
                start_date,
                end_date,
                account_id,
            )
            .where(Transaction.amount > 0, Transaction.merchant_name.is_not(None))
            .group_by(Transaction.merchant_name)
            .order_by(total.desc(), Transaction.merchant_name)
            .limit(limit)
        )
        return list(await self.session.execute(query))
