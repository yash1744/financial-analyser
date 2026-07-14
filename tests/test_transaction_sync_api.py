"""Integration test for POST /transactions/sync: real Postgres, fake Plaid.

Scripted sync cycles: initial backfill (with auto account sync), no-op,
modify+remove, crash-replay (same window re-served → must converge, not
duplicate), and the login-required failure path.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_plaid_service, get_token_cipher
from app.main import app
from app.models.category import Category
from app.models.plaid_item import PlaidItem
from app.models.plaid_sync_state import PlaidSyncState
from app.models.raw_plaid_transaction import RawPlaidTransaction
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.plaid import (
    AccountsSnapshot,
    ExchangedPublicToken,
    TransactionsSyncResult,
)
from app.services.exceptions import PlaidItemLoginRequiredError
from app.utils.crypto import TokenCipher


def txn(
    txn_id: str,
    account_id: str,
    amount: float,
    name: str,
    when: Any,
    pfc: tuple[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transaction_id": txn_id,
        "account_id": account_id,
        "amount": amount,
        "date": when,
        "name": name,
        "merchant_name": name,
        "iso_currency_code": "USD",
        "pending": False,
    }
    if pfc is not None:
        payload["personal_finance_category"] = {
            "primary": pfc[0],
            "detailed": pfc[1],
            "confidence_level": "HIGH",
            "version": "v2",
        }
    return payload


STARBUCKS_PFC = ("FOOD_AND_DRINK", "FOOD_AND_DRINK_COFFEE")


class FakePlaidService:
    def __init__(self) -> None:
        self.script: list[TransactionsSyncResult | Exception] = []
        self.cursors_seen: list[str | None] = []

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(access_token="access-1", item_id="item-txsync-1")

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[
                {"account_id": "chk-1", "name": "Checking", "type": "depository",
                 "subtype": "checking",
                 "balances": {"current": 100.0, "available": 90.0,
                              "iso_currency_code": "USD"}},
                {"account_id": "cc-1", "name": "Card", "type": "credit",
                 "subtype": "credit card",
                 "balances": {"current": 50.0, "available": None,
                              "iso_currency_code": "USD"}},
                {"account_id": "loan-1", "name": "Mortgage", "type": "loan",
                 "subtype": "mortgage",
                 "balances": {"current": 200000.0, "available": None,
                              "iso_currency_code": "USD"}},
            ],
            item={"item_id": "item-txsync-1", "institution_id": "ins_1",
                  "institution_name": "Test Bank"},
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        self.cursors_seen.append(cursor)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


async def test_transaction_sync_flow():
    fake_plaid = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake_plaid
    app.dependency_overrides[get_token_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    user_id: str | None = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/users",
                json={"email": f"tx-sync-{uuid.uuid4().hex[:12]}@example.com"},
            )
            user_id = resp.json()["id"]
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-1"},
            )
            assert resp.status_code == 201, resp.text

            # cycle 1: initial backfill; accounts never synced → auto-sync;
            # t3 belongs to the unsynced loan account → raw kept, normalized
            # skipped. t1 carries a personal_finance_category; t2 doesn't
            # (Plaid can omit it) and must stay uncategorized, not fail.
            fake_plaid.script = [
                TransactionsSyncResult(
                    added=[
                        txn("t1", "chk-1", 12.50, "Starbucks", date(2026, 7, 10),
                            pfc=STARBUCKS_PFC),
                        txn("t2", "cc-1", -45.00, "Refund", "2026-07-11"),
                        txn("t3", "loan-1", 900.00, "Mortgage payment", "2026-07-11"),
                    ],
                    modified=[],
                    removed=[],
                    next_cursor="cur-1",
                )
            ]
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            assert resp.status_code == 200, resp.text
            summary = resp.json()["items"][0]
            assert summary["added"] == 2
            assert summary["skipped"] == 1
            assert summary["next_cursor"] == "cur-1"
            assert fake_plaid.cursors_seen == [None]

            # cycle 2: nothing new; cursor from cycle 1 must be sent to Plaid
            fake_plaid.script = [
                TransactionsSyncResult(added=[], modified=[], removed=[],
                                       next_cursor="cur-2")
            ]
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            summary = resp.json()["items"][0]
            assert (summary["added"], summary["modified"], summary["removed"]) == (0, 0, 0)
            assert fake_plaid.cursors_seen == [None, "cur-1"]

            # cycle 3: t1 modified (new amount), t2 removed
            modify_step = TransactionsSyncResult(
                added=[],
                modified=[txn("t1", "chk-1", 15.00, "Starbucks Reserve", "2026-07-10",
                              pfc=STARBUCKS_PFC)],
                removed=[{"transaction_id": "t2", "account_id": "cc-1"}],
                next_cursor="cur-3",
            )
            fake_plaid.script = [modify_step]
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            summary = resp.json()["items"][0]
            assert summary["modified"] == 1
            assert summary["removed"] == 1

            # cycle 4: crash-replay — Plaid re-serves the same window
            # (as after a crash before the cursor commit); must converge
            fake_plaid.script = [modify_step.model_copy(deep=True)]
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            summary = resp.json()["items"][0]
            assert (summary["added"], summary["modified"], summary["removed"]) == (0, 0, 0)

            # cycle 5: the issue-#1 scenario — a transaction synced before
            # categorization existed (category_id NULL, raw payload intact)
            # must be backfilled from the raw audit trail by the next sync
            from app.db.session import SessionFactory
            from app.models.transaction import Transaction as Txn

            async with SessionFactory() as session:
                t1_row = (
                    await session.execute(
                        select(Txn).where(Txn.plaid_transaction_id == "t1")
                    )
                ).scalars().one()
                assert t1_row.category_id is not None  # categorized by sync
                t1_row.category_id = None  # simulate pre-fix data
                await session.commit()

            fake_plaid.script = [
                TransactionsSyncResult(added=[], modified=[], removed=[],
                                       next_cursor="cur-4")
            ]
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            assert resp.status_code == 200

            # cycle 6: Plaid demands re-auth
            fake_plaid.script = [
                PlaidItemLoginRequiredError(
                    "reconnect", error_code="ITEM_LOGIN_REQUIRED", error_type="ITEM_ERROR"
                )
            ]
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            assert resp.status_code == 409

        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            transactions = {
                t.plaid_transaction_id: t
                for t in (await session.execute(select(Transaction))).scalars()
                if t.plaid_transaction_id in {"t1", "t2", "t3"}
            }
            assert set(transactions) == {"t1"}  # t2 removed, t3 never normalized
            t1 = transactions["t1"]
            assert t1.amount == Decimal("15.00")
            assert t1.merchant_name == "Starbucks Reserve"
            assert t1.transaction_type == "debit"
            assert t1.transaction_date == date(2026, 7, 10)

            # categorized (and re-categorized by the backfill in cycle 5):
            # detailed "Coffee" under primary "Food and Drink"
            assert t1.category_id is not None
            coffee = await session.get(Category, t1.category_id)
            assert coffee.name == "Coffee"
            parent = await session.get(Category, coffee.parent_category_id)
            assert parent.name == "Food and Drink"

            raws = {
                r.plaid_transaction_id: r
                for r in (await session.execute(select(RawPlaidTransaction))).scalars()
                if r.plaid_transaction_id in {"t1", "t2", "t3"}
            }
            assert len(raws) == 3  # raw audit trail survives removal
            assert raws["t1"].processing_status == "processed"
            assert raws["t1"].raw_payload["amount"] == 15.00
            assert raws["t3"].processing_status == "skipped"

            # scoped to this test's item — the dev DB may hold other sync states
            state = (
                await session.execute(
                    select(PlaidSyncState)
                    .join(PlaidItem, PlaidSyncState.plaid_item_id == PlaidItem.id)
                    .where(PlaidItem.plaid_item_id == "item-txsync-1")
                )
            ).scalars().one()
            assert state.cursor == "cur-4"  # failed cycle 6 did not advance it
            assert state.sync_status == "error"
            assert state.last_synced_at is not None

            user = await session.get(User, uuid.UUID(user_id))
            await session.delete(user)  # cascades items/accounts/transactions/raws
            await session.commit()
    finally:
        app.dependency_overrides.clear()
