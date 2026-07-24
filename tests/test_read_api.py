"""Integration tests for GET /accounts, /transactions, /categories."""

import uuid
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_plaid_service, get_token_cipher
from app.main import app
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.plaid import (
    AccountsSnapshot,
    ExchangedPublicToken,
    TransactionsSyncResult,
)
from app.utils.crypto import TokenCipher
from tests.conftest import register_user


def txn(
    txn_id: str,
    account_id: str,
    amount: float,
    name: str,
    when: str,
    pfc: str | None = None,
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
        payload["personal_finance_category"] = {"primary": pfc, "detailed": pfc}
    return payload


class FakePlaidService:
    def __init__(self) -> None:
        self.sync_result = TransactionsSyncResult(
            added=[], modified=[], removed=[], next_cursor="cur-1"
        )

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(
            access_token="access-1", item_id=f"item-read-{public_token}"
        )

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
            ],
            item={"item_id": "item-read-1", "institution_id": "ins_1",
                  "institution_name": "Test Bank"},
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        return self.sync_result


async def test_read_apis():
    fake_plaid = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake_plaid
    app.dependency_overrides[get_token_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    created_user_ids: list[str] = []
    category_id: uuid.UUID | None = None
    category2_id: uuid.UUID | None = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # seed: user + item + 2 accounts + 5 transactions via the sync pipeline
            headers, user_id = await register_user(client)
            created_user_ids.append(user_id)
            await client.post(
                "/api/v1/plaid/exchange-token",
                json={"public_token": "1"},
                headers=headers,
            )
            fake_plaid.sync_result = TransactionsSyncResult(
                added=[
                    # t1 → expense, t3 (money in, spending category) → refund;
                    # the rest have no category data → unknown
                    txn("t1", "chk-1", 10.00, "Alpha Coffee", "2026-07-01",
                        pfc="FOOD_AND_DRINK"),
                    txn("t2", "chk-1", 25.50, "Beta Grocers", "2026-07-05"),
                    txn("t3", "cc-1", -40.00, "Gamma Refund", "2026-07-08",
                        pfc="GENERAL_MERCHANDISE"),
                    txn("t4", "cc-1", 99.99, "Delta Air", "2026-07-10"),
                    txn("t5", "chk-1", 5.00, "Epsilon Snacks", "2026-06-15"),
                ],
                modified=[],
                removed=[],
                next_cursor="cur-1",
            )
            resp = await client.post(
                "/api/v1/transactions/sync", json={}, headers=headers
            )
            assert resp.json()["items"][0]["added"] == 5

            # attach categories to t1 and t4 directly (no category write API yet)
            from app.db.session import SessionFactory

            async with SessionFactory() as session:
                category = Category(name=f"Coffee-{uuid.uuid4().hex[:6]}")
                category2 = Category(name=f"Travel-{uuid.uuid4().hex[:6]}")
                session.add_all([category, category2])
                await session.flush()
                category_id = category.id
                category2_id = category2.id
                t1 = (
                    await session.execute(
                        select(Transaction).where(Transaction.plaid_transaction_id == "t1")
                    )
                ).scalar_one()
                t1.category_id = category.id
                t4 = (
                    await session.execute(
                        select(Transaction).where(Transaction.plaid_transaction_id == "t4")
                    )
                ).scalar_one()
                t4.category_id = category2.id
                await session.commit()

            # GET /accounts: clean DTO, no ORM leakage
            resp = await client.get("/api/v1/accounts", headers=headers)
            assert resp.status_code == 200
            accounts = resp.json()
            assert len(accounts) == 2
            assert set(accounts[0]) == {
                "id", "plaid_account_id", "name", "nickname", "display_name",
                "account_type", "account_subtype", "current_balance",
                "available_balance", "currency",
            }
            chk_id = next(a["id"] for a in accounts if a["plaid_account_id"] == "chk-1")
            cc_id = next(a["id"] for a in accounts if a["plaid_account_id"] == "cc-1")

            resp = await client.get("/api/v1/accounts")
            assert resp.status_code == 401

            # GET /transactions: default sort = date desc
            resp = await client.get("/api/v1/transactions", headers=headers)
            body = resp.json()
            assert body["total"] == 5
            assert body["total_pages"] == 1
            assert [t["plaid_transaction_id"] for t in body["items"]][:2] == ["t4", "t3"]
            assert set(body["items"][0]) == {
                "id", "account_id", "plaid_transaction_id", "transaction_date",
                "merchant_name", "amount", "currency", "category_id",
                "transaction_type", "classification", "pending", "created_at",
                "labels",
            }
            assert body["items"][0]["labels"] == []
            # rows created without an explicit classification default to it
            assert body["items"][0]["classification"] == "unknown"

            # date range filter (inclusive both ends)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "start_date": "2026-07-01", "end_date": "2026-07-08",
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t1", "t2", "t3"}

            # amount filters
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "min_amount": "10",
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t1", "t2", "t4"}
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "max_amount": "0",
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t3"}

            # account filter (single value)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "account_ids": [chk_id],
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t1", "t2", "t5"}
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "account_ids": [cc_id],
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t3", "t4"}
            # account filter (multiple values → OR within the filter)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "account_ids": [chk_id, cc_id],
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {
                "t1", "t2", "t3", "t4", "t5",
            }

            # category filter (single value)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "category_ids": [str(category_id)],
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t1"]
            # category filter (multiple values → OR within the filter)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "category_ids": [str(category_id), str(category2_id)],
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t1", "t4"}

            # classification filter (single value)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "classifications": ["expense"],
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t1"]
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "classifications": ["refund"],
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t3"]
            # classification filter (multiple values → OR within the filter)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "classifications": ["expense", "refund"],
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t1", "t3"}
            # different filter groups combine with AND
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "classifications": ["unknown"], "account_ids": [chk_id],
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t2", "t5"}
            # invalid value is rejected by schema validation
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "classifications": ["bogus"],
            })
            assert resp.status_code == 422

            # merchant filter: case-insensitive substring match on the REST
            # route (issue #43 — previously only exercised via the AI tool,
            # never through GET /transactions directly)
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "merchant": "coffee",
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t1"]
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "merchant": "Alpha Coffee",  # the full name, as the UI sends it
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t1"]
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "merchant": "no-such-merchant",
            })
            assert resp.json()["items"] == []
            # combines with other filters, same as classification above:
            # "r" alone matches Beta Grocers/t2, Gamma Refund/t3, Delta Air/t4
            # (spanning both accounts); adding account_id narrows to just t2
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "merchant": "r",
            })
            assert {t["plaid_transaction_id"] for t in resp.json()["items"]} == {"t2", "t3", "t4"}
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "merchant": "r", "account_ids": [chk_id],
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t2"]

            # sorting
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "sort_by": "amount", "sort_dir": "asc",
            })
            assert resp.json()["items"][0]["plaid_transaction_id"] == "t3"
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "sort_by": "merchant_name", "sort_dir": "asc",
            })
            assert resp.json()["items"][0]["merchant_name"] == "Alpha Coffee"

            # pagination
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "page_size": 2, "page": 1,
            })
            body = resp.json()
            assert [t["plaid_transaction_id"] for t in body["items"]] == ["t4", "t3"]
            assert body["total"] == 5
            assert body["total_pages"] == 3
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "page_size": 2, "page": 3,
            })
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["t5"]

            # invalid ranges → 422
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "start_date": "2026-07-10", "end_date": "2026-07-01",
            })
            assert resp.status_code == 422
            resp = await client.get("/api/v1/transactions", headers=headers, params={
                "min_amount": "100", "max_amount": "1",
            })
            assert resp.status_code == 422

            # another user sees nothing of this data
            headers_other, other_id = await register_user(client)
            created_user_ids.append(other_id)
            resp = await client.get("/api/v1/transactions", headers=headers_other)
            assert resp.json()["total"] == 0
            resp = await client.get("/api/v1/accounts", headers=headers_other)
            assert resp.json() == []

            # GET /categories
            resp = await client.get("/api/v1/categories", headers=headers)
            assert resp.status_code == 200
            match = [c for c in resp.json() if c["id"] == str(category_id)]
            assert len(match) == 1
            assert match[0]["parent_category_id"] is None

        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            for uid in created_user_ids:
                user = await session.get(User, uuid.UUID(uid))
                await session.delete(user)
            for cid in (category_id, category2_id):
                if cid is not None:
                    category = await session.get(Category, cid)
                    await session.delete(category)
            await session.commit()
    finally:
        app.dependency_overrides.clear()
