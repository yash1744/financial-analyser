"""Integration tests for the analytics endpoints: real Postgres, fake Plaid.

Seeded data (July / June 2026):
  t1 chk 2026-07-01  10.00  Alpha Coffee   [Coffee]
  t2 chk 2026-07-05  25.50  Beta Grocers
  t3 cc  2026-07-08 -40.00  Gamma Refund   (income)
  t4 cc  2026-07-10  99.99  Delta Air
  t5 chk 2026-06-15   5.00  Epsilon Snacks
  t6 chk 2026-06-20  20.00  Alpha Coffee   [Coffee]
"""

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


def txn(txn_id: str, account_id: str, amount: float, name: str, when: str) -> dict[str, Any]:
    return {
        "transaction_id": txn_id,
        "account_id": account_id,
        "amount": amount,
        "date": when,
        "name": name,
        "merchant_name": name,
        "iso_currency_code": "USD",
        "pending": False,
    }


class FakePlaidService:
    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(access_token="access-1", item_id="item-analytics-1")

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
            item={"item_id": "item-analytics-1", "institution_id": "ins_1",
                  "institution_name": "Test Bank"},
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        return TransactionsSyncResult(
            added=[
                txn("t1", "chk-1", 10.00, "Alpha Coffee", "2026-07-01"),
                txn("t2", "chk-1", 25.50, "Beta Grocers", "2026-07-05"),
                txn("t3", "cc-1", -40.00, "Gamma Refund", "2026-07-08"),
                txn("t4", "cc-1", 99.99, "Delta Air", "2026-07-10"),
                txn("t5", "chk-1", 5.00, "Epsilon Snacks", "2026-06-15"),
                txn("t6", "chk-1", 20.00, "Alpha Coffee", "2026-06-20"),
            ],
            modified=[],
            removed=[],
            next_cursor="cur-1",
        )


async def test_analytics_apis():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: FakePlaidService()
    app.dependency_overrides[get_token_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    user_id: str | None = None
    category_id: uuid.UUID | None = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, user_id = await register_user(client)
            await client.post(
                "/api/v1/plaid/exchange-token",
                json={"public_token": "p1"},
                headers=headers,
            )
            resp = await client.post(
                "/api/v1/transactions/sync", json={}, headers=headers
            )
            assert resp.json()["items"][0]["added"] == 6

            # categorize the two Alpha Coffee transactions
            from app.db.session import SessionFactory

            async with SessionFactory() as session:
                category = Category(name=f"Coffee-{uuid.uuid4().hex[:6]}")
                session.add(category)
                await session.flush()
                category_id = category.id
                rows = (
                    await session.execute(
                        select(Transaction).where(
                            Transaction.plaid_transaction_id.in_(["t1", "t6"])
                        )
                    )
                ).scalars()
                for row in rows:
                    row.category_id = category.id
                await session.commit()

            # --- monthly-spending ---
            resp = await client.get(
                "/api/v1/analytics/monthly-spending", headers=headers
            )
            assert resp.status_code == 200, resp.text
            months = resp.json()["months"]
            assert [m["month"] for m in months] == ["2026-06", "2026-07"]
            june, july = months
            assert (june["spending"], june["income"], june["net"]) == ("25.00", "0.00", "25.00")
            assert june["transaction_count"] == 2
            assert (july["spending"], july["income"], july["net"]) == (
                "135.49", "40.00", "95.49",
            )
            assert july["transaction_count"] == 4

            # account filter: checking only
            resp = await client.get("/api/v1/accounts", headers=headers)
            chk_id = next(
                a["id"] for a in resp.json() if a["plaid_account_id"] == "chk-1"
            )
            resp = await client.get(
                "/api/v1/analytics/monthly-spending",
                headers=headers, params={"account_id": chk_id},
            )
            months = resp.json()["months"]
            assert [(m["month"], m["spending"]) for m in months] == [
                ("2026-06", "25.00"),
                ("2026-07", "35.50"),
            ]

            # date filter narrows to July
            resp = await client.get(
                "/api/v1/analytics/monthly-spending",
                headers=headers, params={"start_date": "2026-07-01"},
            )
            assert [m["month"] for m in resp.json()["months"]] == ["2026-07"]

            # --- category-breakdown ---
            resp = await client.get(
                "/api/v1/analytics/category-breakdown", headers=headers
            )
            body = resp.json()
            assert body["total_spending"] == "160.49"
            uncategorized, coffee = body["categories"]  # ordered by total desc
            assert uncategorized["category_name"] == "Uncategorized"
            assert uncategorized["category_id"] is None
            assert (uncategorized["total"], uncategorized["share_pct"]) == ("130.49", 81.31)
            assert coffee["category_id"] == str(category_id)
            assert (coffee["total"], coffee["transaction_count"], coffee["share_pct"]) == (
                "30.00", 2, 18.69,
            )

            # --- top-merchants ---
            resp = await client.get(
                "/api/v1/analytics/top-merchants",
                headers=headers, params={"limit": 2},
            )
            merchants = [
                (m["merchant_name"], m["total"], m["transaction_count"])
                for m in resp.json()["merchants"]
            ]
            # refund (negative) is excluded from spending ranks
            assert merchants == [("Delta Air", "99.99", 1), ("Alpha Coffee", "30.00", 2)]

            # --- month-over-month (today is in 2026-07; June+July in window) ---
            resp = await client.get(
                "/api/v1/analytics/month-over-month",
                headers=headers, params={"months": 6},
            )
            points = resp.json()["months"]
            assert len(points) == 6
            assert points[0]["change"] is None  # first month has no baseline
            june_pt, july_pt = points[-2], points[-1]
            assert (june_pt["month"], june_pt["spending"]) == ("2026-06", "25.00")
            assert june_pt["change_pct"] is None  # baseline month was 0
            assert (july_pt["month"], july_pt["spending"]) == ("2026-07", "135.49")
            assert july_pt["change"] == "110.49"
            assert july_pt["change_pct"] == 441.96
            zero_filled = points[1]
            assert (zero_filled["spending"], zero_filled["change"]) == ("0.00", "0.00")

            # --- validation / errors ---
            # identity comes from the token; no token → 401
            resp = await client.get("/api/v1/analytics/monthly-spending")
            assert resp.status_code == 401
            resp = await client.get(
                "/api/v1/analytics/category-breakdown",
                headers=headers, params={"start_date": "2026-07-10",
                        "end_date": "2026-07-01"},
            )
            assert resp.status_code == 422
            resp = await client.get(
                "/api/v1/analytics/top-merchants",
                headers=headers, params={"limit": 100},
            )
            assert resp.status_code == 422

        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            user = await session.get(User, uuid.UUID(user_id))
            await session.delete(user)
            if category_id is not None:
                category = await session.get(Category, category_id)
                await session.delete(category)
            await session.commit()
    finally:
        app.dependency_overrides.clear()
