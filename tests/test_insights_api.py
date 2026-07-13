"""Integration tests for the insights endpoints and LLM tool wrappers:
real Postgres, fake Plaid.

Seeded relative to today (D = days ago), all on one checking account:
  Netflix       15.49 at D-100, D-70, D-40, D-10   → monthly recurring
  Gym Co        45.00 at D-49, D-35, D-21, D-7     → biweekly recurring
  Corner Store  50 / 5 / 9 at D-31, D-17, D-3      → steady cadence, amounts
                                                     too noisy → NOT recurring
  Cafe          20.00 at D-2
  Payroll    -2000.00 at D-5                        → income
"""

import uuid
from datetime import date, timedelta
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_plaid_service, get_token_cipher
from app.llm.tools import UnknownToolError, build_finance_toolset
from app.main import app
from app.schemas.plaid import (
    AccountsSnapshot,
    ExchangedPublicToken,
    TransactionsSyncResult,
)
from app.utils.crypto import TokenCipher

TODAY = date.today()


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def txn(txn_id: str, amount: float, name: str, when: str) -> dict[str, Any]:
    return {
        "transaction_id": txn_id,
        "account_id": "chk-1",
        "amount": amount,
        "date": when,
        "name": name,
        "merchant_name": name,
        "iso_currency_code": "USD",
        "pending": False,
    }


SEED = [
    txn("n1", 15.49, "Netflix", days_ago(100)),
    txn("n2", 15.49, "Netflix", days_ago(70)),
    txn("n3", 15.49, "Netflix", days_ago(40)),
    txn("n4", 15.49, "Netflix", days_ago(10)),
    txn("g1", 45.00, "Gym Co", days_ago(49)),
    txn("g2", 45.00, "Gym Co", days_ago(35)),
    txn("g3", 45.00, "Gym Co", days_ago(21)),
    txn("g4", 45.00, "Gym Co", days_ago(7)),
    txn("c1", 50.00, "Corner Store", days_ago(31)),
    txn("c2", 5.00, "Corner Store", days_ago(17)),
    txn("c3", 9.00, "Corner Store", days_ago(3)),
    txn("f1", 20.00, "Cafe", days_ago(2)),
    txn("p1", -2000.00, "Payroll", days_ago(5)),
]


class FakePlaidService:
    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(access_token="access-1", item_id="item-insights-1")

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[
                {"account_id": "chk-1", "name": "Checking", "type": "depository",
                 "subtype": "checking",
                 "balances": {"current": 100.0, "available": 90.0,
                              "iso_currency_code": "USD"}},
            ],
            item={"item_id": "item-insights-1", "institution_id": "ins_1",
                  "institution_name": "Test Bank"},
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        return TransactionsSyncResult(
            added=SEED, modified=[], removed=[], next_cursor="cur-1"
        )


async def test_insights_apis_and_llm_tools():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: FakePlaidService()
    app.dependency_overrides[get_token_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/users",
                json={"email": f"insights-{uuid.uuid4().hex[:12]}@example.com"},
            )
            user_id = resp.json()["id"]
            await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "p1"},
            )
            resp = await client.post(
                "/api/v1/transactions/sync", json={"user_id": user_id}
            )
            assert resp.json()["items"][0]["added"] == len(SEED)

            # --- spending-summary (explicit range covering everything) ---
            resp = await client.get(
                "/api/v1/insights/spending-summary",
                params={
                    "user_id": user_id,
                    "start_date": days_ago(120),
                    "end_date": TODAY.isoformat(),
                },
            )
            assert resp.status_code == 200, resp.text
            summary = resp.json()
            # 4×15.49 + 4×45 + 64 + 20 = 325.96 out; 2000 in
            assert summary["total_spending"] == "325.96"
            assert summary["total_income"] == "2000.00"
            assert summary["net"] == "-1674.04"
            assert summary["transaction_count"] == len(SEED)
            assert summary["average_transaction"] == "27.16"  # 325.96 / 12 outflows
            assert summary["daily_average_spending"] == "2.69"  # / 121 days
            assert summary["top_merchant"] == {"name": "Gym Co", "total": "180.00"}
            assert summary["top_category"] == {
                "name": "Uncategorized", "total": "325.96",
            }

            # empty range → zeros, no averages
            resp = await client.get(
                "/api/v1/insights/spending-summary",
                params={
                    "user_id": user_id,
                    "start_date": (TODAY + timedelta(days=30)).isoformat(),
                    "end_date": (TODAY + timedelta(days=30)).isoformat(),
                },
            )
            empty = resp.json()
            assert empty["total_spending"] == "0.00"
            assert empty["transaction_count"] == 0
            assert empty["average_transaction"] is None
            assert empty["top_merchant"] is None

            # --- compare-spending (explicit periods) ---
            resp = await client.get(
                "/api/v1/insights/compare-spending",
                params={
                    "user_id": user_id,
                    "baseline_start": days_ago(60),
                    "baseline_end": days_ago(31),
                    "comparison_start": days_ago(30),
                    "comparison_end": TODAY.isoformat(),
                },
            )
            assert resp.status_code == 200, resp.text
            compare = resp.json()
            # baseline: Netflix(40) + Gym(49,35) + Corner(31) = 15.49+90+50
            assert compare["baseline"]["total_spending"] == "155.49"
            # comparison: Netflix(10) + Gym(21,7) + Corner(17,3) + Cafe = 139.49
            assert compare["comparison"]["total_spending"] == "139.49"
            assert compare["comparison"]["total_income"] == "2000.00"
            assert compare["spending_change"] == "-16.00"
            assert compare["spending_change_pct"] == -10.29
            [category] = compare["category_changes"]
            assert category["category_name"] == "Uncategorized"
            assert category["change"] == "-16.00"

            # default (no dates): previous full month vs current month to date
            resp = await client.get(
                "/api/v1/insights/compare-spending", params={"user_id": user_id}
            )
            body = resp.json()
            prev_month_start = (
                TODAY.replace(day=1) - timedelta(days=1)
            ).replace(day=1)
            assert body["baseline"]["start_date"] == prev_month_start.isoformat()
            assert body["comparison"]["end_date"] == TODAY.isoformat()

            # partial period spec is rejected
            resp = await client.get(
                "/api/v1/insights/compare-spending",
                params={"user_id": user_id, "baseline_start": days_ago(60)},
            )
            assert resp.status_code == 422

            # --- recurring-transactions ---
            resp = await client.get(
                "/api/v1/insights/recurring-transactions",
                params={"user_id": user_id},
            )
            assert resp.status_code == 200, resp.text
            items = resp.json()["items"]
            # Corner Store's cadence is steady but amounts aren't → excluded
            assert [(i["merchant_name"], i["cadence"]) for i in items] == [
                ("Gym Co", "biweekly"),
                ("Netflix", "monthly"),
            ]
            gym, netflix = items
            assert gym["average_amount"] == "45.00"
            assert gym["occurrence_count"] == 4
            assert gym["next_expected_date"] == days_ago(-7)  # last + 14
            assert netflix["average_amount"] == "15.49"
            assert netflix["next_expected_date"] == days_ago(-20)  # last + 30

            # --- transaction search: merchant text filter ---
            resp = await client.get(
                "/api/v1/transactions",
                params={"user_id": user_id, "merchant": "net"},
            )
            body = resp.json()
            assert body["total"] == 4
            assert all("Netflix" == t["merchant_name"] for t in body["items"])

            # --- LLM tools: same services, same numbers ---
            from app.db.session import SessionFactory

            async with SessionFactory() as session:
                toolset = build_finance_toolset(session, uuid.UUID(user_id))

                definitions = toolset.definitions()
                assert sorted(d["name"] for d in definitions) == [
                    "compare_spending",
                    "get_recurring_transactions",
                    "get_spending_by_category",
                    "get_spending_summary",
                    "search_transactions",
                ]
                # user_id is injected by the toolset, never exposed to the model
                for definition in definitions:
                    assert "user_id" not in definition["input_schema"]["properties"]

                tool_summary = await toolset.execute(
                    "get_spending_summary",
                    {"start_date": days_ago(120), "end_date": TODAY.isoformat()},
                )
                assert tool_summary == summary  # byte-for-byte the REST answer

                tool_recurring = await toolset.execute(
                    "get_recurring_transactions", {}
                )
                assert [i["merchant_name"] for i in tool_recurring["items"]] == [
                    "Gym Co", "Netflix",
                ]

                tool_search = await toolset.execute(
                    "search_transactions", {"merchant": "corner store"}
                )
                assert tool_search["total"] == 3

                tool_categories = await toolset.execute(
                    "get_spending_by_category", {"start_date": days_ago(120)}
                )
                assert tool_categories["total_spending"] == "325.96"

                try:
                    await toolset.execute("drop_tables", {})
                    raise AssertionError("unknown tool must raise")
                except UnknownToolError:
                    pass
    finally:
        app.dependency_overrides.clear()
