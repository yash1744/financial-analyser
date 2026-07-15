import uuid
from datetime import date
from decimal import Decimal
from itertools import batched

from sqlalchemy import Row, delete, func, select

from app.models.account import Account
from app.models.enums import TransactionClassification
from app.models.plaid_item import PlaidItem
from app.models.raw_plaid_transaction import RawPlaidTransaction
from app.models.transaction import Transaction
from app.repositories.base import BaseRepository

_IN_CLAUSE_CHUNK = 1000

_SORT_COLUMNS = {
    "transaction_date": Transaction.transaction_date,
    "amount": Transaction.amount,
    "merchant_name": Transaction.merchant_name,
}


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user text matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TransactionRepository(BaseRepository):
    async def map_by_plaid_ids(self, ids: list[str]) -> dict[str, Transaction]:
        found: dict[str, Transaction] = {}
        for chunk in batched(ids, _IN_CLAUSE_CHUNK, strict=False):
            result = await self.session.execute(
                select(Transaction).where(Transaction.plaid_transaction_id.in_(chunk))
            )
            for row in result.scalars():
                found[row.plaid_transaction_id] = row
        return found

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        return transaction

    async def get_for_user(
        self, transaction_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction | None:
        """The transaction only if it belongs to this user (via the
        account→item→user chain); None hides foreign rows entirely."""
        result = await self.session.execute(
            select(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .join(PlaidItem, Account.plaid_item_id == PlaidItem.id)
            .where(Transaction.id == transaction_id, PlaidItem.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
        classification: TransactionClassification | None = None,
        merchant: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        sort_by: str = "transaction_date",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Transaction], int]:
        """Filtered, sorted page of a user's transactions plus the total count."""
        conditions = [PlaidItem.user_id == user_id]
        if account_id is not None:
            conditions.append(Transaction.account_id == account_id)
        if category_id is not None:
            conditions.append(Transaction.category_id == category_id)
        if classification is not None:
            conditions.append(Transaction.classification == classification)
        if merchant is not None:
            conditions.append(
                Transaction.merchant_name.ilike(f"%{_escape_like(merchant)}%")
            )
        if start_date is not None:
            conditions.append(Transaction.transaction_date >= start_date)
        if end_date is not None:
            conditions.append(Transaction.transaction_date <= end_date)
        if min_amount is not None:
            conditions.append(Transaction.amount >= min_amount)
        if max_amount is not None:
            conditions.append(Transaction.amount <= max_amount)

        scoped = (
            select(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .join(PlaidItem, Account.plaid_item_id == PlaidItem.id)
            .where(*conditions)
        )

        total = await self.session.scalar(
            select(func.count()).select_from(scoped.subquery())
        )

        sort_column = _SORT_COLUMNS[sort_by]
        ordering = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
        result = await self.session.execute(
            # id as tiebreaker keeps pagination stable across equal sort keys
            scoped.order_by(ordering, Transaction.id).limit(limit).offset(offset)
        )
        return list(result.scalars()), total or 0

    async def recurring_candidates(
        self, user_id: uuid.UUID, since: date, min_occurrences: int
    ) -> list[Row]:
        """Outflow rows for merchants charged >= min_occurrences times since
        `since`, ordered per merchant by date. Cadence detection happens in
        the service — SQL only narrows to plausible candidates."""
        counted = (
            select(
                Transaction.merchant_name,
                Transaction.transaction_date,
                Transaction.amount,
                Transaction.currency,
                func.count()
                .over(partition_by=Transaction.merchant_name)
                .label("occurrences"),
            )
            .join(Account, Transaction.account_id == Account.id)
            .join(PlaidItem, Account.plaid_item_id == PlaidItem.id)
            .where(
                PlaidItem.user_id == user_id,
                Transaction.amount > 0,
                Transaction.merchant_name.is_not(None),
                Transaction.transaction_date >= since,
            )
            .subquery()
        )
        query = (
            select(counted)
            .where(counted.c.occurrences >= min_occurrences)
            .order_by(counted.c.merchant_name, counted.c.transaction_date)
        )
        return list(await self.session.execute(query))

    async def list_unenriched_with_raw(
        self, plaid_item_id: uuid.UUID
    ) -> list[tuple[Transaction, dict]]:
        """An item's normalized transactions still missing a category or a
        classification, paired with their verbatim Plaid payloads (for
        re-derivation)."""
        result = await self.session.execute(
            select(Transaction, RawPlaidTransaction.raw_payload)
            .join(Account, Transaction.account_id == Account.id)
            .join(
                RawPlaidTransaction,
                RawPlaidTransaction.plaid_transaction_id
                == Transaction.plaid_transaction_id,
            )
            .where(
                Account.plaid_item_id == plaid_item_id,
                Transaction.category_id.is_(None)
                | (Transaction.classification == TransactionClassification.UNKNOWN),
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def delete_by_plaid_ids(self, ids: list[str]) -> int:
        """Delete normalized rows for Plaid-removed transactions; returns count."""
        deleted = 0
        for chunk in batched(ids, _IN_CLAUSE_CHUNK, strict=False):
            result = await self.session.execute(
                delete(Transaction).where(Transaction.plaid_transaction_id.in_(chunk))
            )
            deleted += result.rowcount or 0
        return deleted
