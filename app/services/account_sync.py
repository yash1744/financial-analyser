"""Synchronizes accounts under connected Plaid items into the accounts table.

Upserts keyed on plaid_account_id: fetching twice never duplicates,
renamed accounts are updated in place, balances refresh on every sync.
"""

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import PlaidItemStatus
from app.models.plaid_item import PlaidItem
from app.repositories.account import AccountRepository
from app.repositories.plaid_item import PlaidItemRepository
from app.repositories.user import UserRepository
from app.schemas.account import AccountResponse, ItemAccountsSyncSummary
from app.services.exceptions import NotFoundError, PlaidItemLoginRequiredError
from app.services.plaid import PlaidService
from app.utils.crypto import TokenCipher

logger = logging.getLogger(__name__)

# Spending-relevant account types; extend when investments/loans matter
ACCOUNT_TYPES_TO_SYNC = {"depository", "credit"}


def _to_decimal(value: Any) -> Decimal | None:
    # Plaid sends floats; going through str avoids float artifacts
    return None if value is None else Decimal(str(value))


class AccountSyncService:
    def __init__(self, session: AsyncSession, plaid: PlaidService, cipher: TokenCipher) -> None:
        self.session = session
        self.plaid = plaid
        self.cipher = cipher
        self.users = UserRepository(session)
        self.items = PlaidItemRepository(session)
        self.accounts = AccountRepository(session)

    async def sync_accounts(
        self, user_id: uuid.UUID, item_id: uuid.UUID | None = None
    ) -> list[ItemAccountsSyncSummary]:
        if await self.users.get(user_id) is None:
            raise NotFoundError(f"user {user_id} does not exist")

        if item_id is not None:
            item = await self.items.get(item_id)
            if item is None or item.user_id != user_id:
                raise NotFoundError(f"plaid item {item_id} does not exist for this user")
            items = [item]
        else:
            # retired connections (replaced re-links) are dead tokens —
            # syncing them can only fail
            items = [
                item
                for item in await self.items.list_for_user(user_id)
                if item.status != PlaidItemStatus.DISCONNECTED
            ]

        summaries = [await self.sync_item(item) for item in items]
        await self.session.commit()
        return summaries

    async def sync_item(self, item: PlaidItem) -> ItemAccountsSyncSummary:
        """Sync one item's accounts. Flushes only — the caller commits."""
        access_token = self.cipher.decrypt(item.access_token_encrypted)
        try:
            snapshot = await self.plaid.get_accounts(access_token)
        except PlaidItemLoginRequiredError:
            # Persist the broken state so the UI can prompt re-auth,
            # then let the API layer report the 409
            item.status = PlaidItemStatus.LOGIN_REQUIRED
            await self.session.commit()
            raise

        if item.status != PlaidItemStatus.ACTIVE:
            item.status = PlaidItemStatus.ACTIVE  # the connection evidently works again

        existing = {
            account.plaid_account_id: account
            for account in await self.accounts.list_for_item(item.id)
        }

        created = updated = skipped = 0
        synced: list[Account] = []
        for raw in snapshot.accounts:
            account_type = str(raw.get("type", ""))
            if account_type not in ACCOUNT_TYPES_TO_SYNC:
                skipped += 1
                continue

            account = existing.get(raw["account_id"])
            if account is None:
                account = await self._create_account(item, raw, account_type)
                created += 1
            elif self._apply_updates(account, raw, account_type):
                updated += 1
            synced.append(account)

        logger.info(
            "Synced accounts for item %s: %d created, %d updated, %d skipped",
            item.plaid_item_id,
            created,
            updated,
            skipped,
        )
        return ItemAccountsSyncSummary(
            item_id=item.id,
            plaid_item_id=item.plaid_item_id,
            institution_name=item.institution_name,
            created=created,
            updated=updated,
            skipped=skipped,
            accounts=[AccountResponse.model_validate(account) for account in synced],
        )

    async def _create_account(
        self, item: PlaidItem, raw: dict[str, Any], account_type: str
    ) -> Account:
        balances = raw.get("balances") or {}
        return await self.accounts.create(
            plaid_item_id=item.id,
            plaid_account_id=raw["account_id"],
            name=raw.get("name") or "Unnamed account",
            account_type=account_type,
            account_subtype=str(raw["subtype"]) if raw.get("subtype") else None,
            current_balance=_to_decimal(balances.get("current")),
            available_balance=_to_decimal(balances.get("available")),
            currency=balances.get("iso_currency_code") or "USD",
        )

    def _apply_updates(self, account: Account, raw: dict[str, Any], account_type: str) -> bool:
        """Copy changed fields onto the row; True if anything changed."""
        balances = raw.get("balances") or {}
        new_values = {
            "name": raw.get("name") or account.name,
            "account_type": account_type,
            "account_subtype": str(raw["subtype"]) if raw.get("subtype") else None,
            "current_balance": _to_decimal(balances.get("current")),
            "available_balance": _to_decimal(balances.get("available")),
            "currency": balances.get("iso_currency_code") or account.currency,
        }
        changed = False
        for field, value in new_values.items():
            if getattr(account, field) != value:
                setattr(account, field, value)
                changed = True
        return changed
