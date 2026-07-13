import uuid
from itertools import batched
from typing import Any

from sqlalchemy import select

from app.models.raw_plaid_transaction import RawPlaidTransaction
from app.repositories.base import BaseRepository

_IN_CLAUSE_CHUNK = 1000


class RawPlaidTransactionRepository(BaseRepository):
    async def map_by_plaid_ids(self, ids: list[str]) -> dict[str, RawPlaidTransaction]:
        found: dict[str, RawPlaidTransaction] = {}
        for chunk in batched(ids, _IN_CLAUSE_CHUNK, strict=False):
            result = await self.session.execute(
                select(RawPlaidTransaction).where(
                    RawPlaidTransaction.plaid_transaction_id.in_(chunk)
                )
            )
            for row in result.scalars():
                found[row.plaid_transaction_id] = row
        return found

    async def create(
        self,
        *,
        plaid_transaction_id: str,
        plaid_item_id: uuid.UUID,
        raw_payload: dict[str, Any],
    ) -> RawPlaidTransaction:
        row = RawPlaidTransaction(
            plaid_transaction_id=plaid_transaction_id,
            plaid_item_id=plaid_item_id,
            raw_payload=raw_payload,
        )
        self.session.add(row)
        await self.session.flush()
        return row
