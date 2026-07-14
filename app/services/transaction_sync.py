"""Plaid /transactions/sync orchestration.

Algorithm per item (all inside ONE database transaction):

1. Load (or create) the plaid_sync_state row and take its cursor.
2. Call Plaid /transactions/sync from that cursor (PlaidService pages
   internally and handles the mutation-during-pagination restart).
3. Land every added/modified payload verbatim in raw_plaid_transactions.
4. Normalize into transactions (upsert keyed on plaid_transaction_id).
5. Delete normalized rows Plaid reports as removed.
6. Save next_cursor + mark state idle, then COMMIT.

Because the cursor is committed atomically with the data it describes, a
crash anywhere before the commit leaves the old cursor in place — the next
run refetches the same window and the upserts/deletes converge to the same
state. That makes the sync at-least-once + idempotent, so duplicates are
impossible (also enforced by the unique constraint on plaid_transaction_id).
"""

import json
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PlaidItemStatus, ProcessingStatus, SyncStatus, TransactionType
from app.models.plaid_item import PlaidItem
from app.models.transaction import Transaction
from app.repositories.account import AccountRepository
from app.repositories.plaid_item import PlaidItemRepository
from app.repositories.plaid_sync_state import PlaidSyncStateRepository
from app.repositories.raw_plaid_transaction import RawPlaidTransactionRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.user import UserRepository
from app.schemas.transaction import ItemTransactionsSyncSummary
from app.services.account_sync import AccountSyncService
from app.services.categorization import CategoryResolver
from app.services.exceptions import (
    NotFoundError,
    PlaidItemLoginRequiredError,
    PlaidServiceError,
)
from app.services.plaid import PlaidService
from app.utils.crypto import TokenCipher

logger = logging.getLogger(__name__)


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    # Plaid's to_dict() contains date/Decimal objects JSONB can't take
    return json.loads(json.dumps(payload, default=str))


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


class TransactionSyncService:
    def __init__(self, session: AsyncSession, plaid: PlaidService, cipher: TokenCipher) -> None:
        self.session = session
        self.plaid = plaid
        self.cipher = cipher
        self.users = UserRepository(session)
        self.items = PlaidItemRepository(session)
        self.accounts = AccountRepository(session)
        self.sync_states = PlaidSyncStateRepository(session)
        self.raws = RawPlaidTransactionRepository(session)
        self.transactions = TransactionRepository(session)
        self.account_sync = AccountSyncService(session, plaid, cipher)
        self.categorizer = CategoryResolver(session)

    async def sync_transactions(
        self, user_id: uuid.UUID, item_id: uuid.UUID | None = None
    ) -> list[ItemTransactionsSyncSummary]:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")

        if item_id is not None:
            item = await self.items.get(item_id)
            if item is None or item.user_id != user_id:
                raise NotFoundError(f"plaid item {item_id} does not exist for this user")
            items = [item]
        else:
            items = await self.items.list_for_user(user_id)

        # Each item commits on its own: a failure in one never rolls
        # back another item's already-synced data.
        return [await self._sync_item(item) for item in items]

    async def _sync_item(self, item: PlaidItem) -> ItemTransactionsSyncSummary:
        state = await self.sync_states.get_for_item(item.id)
        if state is None:
            state = await self.sync_states.create_for_item(item.id)

        access_token = self.cipher.decrypt(item.access_token_encrypted)
        state.sync_status = SyncStatus.SYNCING
        try:
            result = await self.plaid.sync_transactions(access_token, state.cursor)
        except PlaidItemLoginRequiredError:
            item.status = PlaidItemStatus.LOGIN_REQUIRED
            state.sync_status = SyncStatus.ERROR
            await self.session.commit()
            raise
        except PlaidServiceError:
            state.sync_status = SyncStatus.ERROR
            await self.session.commit()
            raise

        changed = result.added + result.modified
        if changed:
            # First transaction sync before any account sync: pull the
            # accounts now so normalization has rows to attach to
            if not await self.accounts.list_for_item(item.id):
                await self.account_sync.sync_item(item)

        added, modified, skipped = await self._apply_changes(item, changed)
        removed = await self.transactions.delete_by_plaid_ids(
            [entry["transaction_id"] for entry in result.removed]
        )
        # Self-heal rows synced before categorization existed (or whose
        # payload lacked a category at the time) from the raw audit trail
        recategorized = await self._backfill_categories(item)
        if recategorized:
            logger.info(
                "Backfilled categories for %d transactions on item %s",
                recategorized,
                item.plaid_item_id,
            )

        now = datetime.now(UTC)
        state.cursor = result.next_cursor
        state.last_synced_at = now
        state.sync_status = SyncStatus.IDLE
        await self.session.commit()

        logger.info(
            "Synced transactions for item %s: +%d ~%d -%d (skipped %d)",
            item.plaid_item_id,
            added,
            modified,
            removed,
            skipped,
        )
        return ItemTransactionsSyncSummary(
            item_id=item.id,
            plaid_item_id=item.plaid_item_id,
            institution_name=item.institution_name,
            added=added,
            modified=modified,
            removed=removed,
            skipped=skipped,
            next_cursor=result.next_cursor,
            last_synced_at=now,
        )

    async def _apply_changes(
        self, item: PlaidItem, changed: list[dict[str, Any]]
    ) -> tuple[int, int, int]:
        """Land raw payloads and upsert normalized rows. Returns (added, modified, skipped)."""
        accounts_by_plaid_id = {
            account.plaid_account_id: account
            for account in await self.accounts.list_for_item(item.id)
        }
        ids = [entry["transaction_id"] for entry in changed]
        raw_by_id = await self.raws.map_by_plaid_ids(ids)
        tx_by_id = await self.transactions.map_by_plaid_ids(ids)

        added = modified = skipped = 0
        now = datetime.now(UTC)
        for entry in changed:
            plaid_txn_id = entry["transaction_id"]
            payload = _jsonable(entry)

            raw = raw_by_id.get(plaid_txn_id)
            if raw is None:
                raw = await self.raws.create(
                    plaid_transaction_id=plaid_txn_id,
                    plaid_item_id=item.id,
                    raw_payload=payload,
                )
                raw_by_id[plaid_txn_id] = raw
            else:
                raw.raw_payload = payload

            account = accounts_by_plaid_id.get(entry.get("account_id"))
            if account is None:
                # e.g. a loan account we deliberately don't sync; raw is
                # kept so it can be reprocessed if the filter widens
                raw.processing_status = ProcessingStatus.SKIPPED
                raw.processed_at = now
                skipped += 1
                continue

            fields = self._normalized_fields(entry, account.id)
            fields["category_id"] = await self.categorizer.resolve(entry)
            transaction = tx_by_id.get(plaid_txn_id)
            if transaction is None:
                transaction = Transaction(plaid_transaction_id=plaid_txn_id, **fields)
                self.transactions.add(transaction)
                tx_by_id[plaid_txn_id] = transaction
                added += 1
            else:
                if self._apply_updates(transaction, fields):
                    modified += 1

            raw.processing_status = ProcessingStatus.PROCESSED
            raw.processed_at = now

        return added, modified, skipped

    async def _backfill_categories(self, item: PlaidItem) -> int:
        """Re-categorize the item's uncategorized transactions from their
        stored raw payloads. Idempotent: rows whose payload has no
        personal_finance_category simply stay uncategorized."""
        recategorized = 0
        for transaction, payload in await self.transactions.list_uncategorized_with_raw(
            item.id
        ):
            category_id = await self.categorizer.resolve(payload)
            if category_id is not None:
                transaction.category_id = category_id
                recategorized += 1
        return recategorized

    @staticmethod
    def _normalized_fields(entry: dict[str, Any], account_id: uuid.UUID) -> dict[str, Any]:
        amount = Decimal(str(entry["amount"]))
        return {
            "account_id": account_id,
            "transaction_date": _as_date(entry["date"]),
            "merchant_name": entry.get("merchant_name") or entry.get("name"),
            "amount": amount,
            "currency": entry.get("iso_currency_code") or "USD",
            # Plaid sign convention: positive = money out
            "transaction_type": (
                TransactionType.DEBIT if amount >= 0 else TransactionType.CREDIT
            ),
            "pending": bool(entry.get("pending", False)),
        }

    @staticmethod
    def _apply_updates(transaction: Transaction, fields: dict[str, Any]) -> bool:
        changed = False
        for field, value in fields.items():
            if getattr(transaction, field) != value:
                setattr(transaction, field, value)
                changed = True
        return changed
