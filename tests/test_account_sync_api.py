"""Integration test for POST /plaid/accounts/sync: real Postgres, fake Plaid.

One test function so the whole flow shares one event loop (the async
engine's pooled connections are loop-bound).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_plaid_service, get_token_cipher
from app.main import app
from app.models.plaid_item import PlaidItem
from app.models.user import User
from app.schemas.plaid import AccountsSnapshot, ExchangedPublicToken, LinkTokenResult
from app.services.exceptions import PlaidItemLoginRequiredError
from app.utils.crypto import TokenCipher
from tests.conftest import register_user


def account(account_id: str, name: str, type_: str, subtype: str, current: float,
            available: float | None = None) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "name": name,
        "type": type_,
        "subtype": subtype,
        "balances": {"current": current, "available": available, "iso_currency_code": "USD"},
    }


class FakePlaidService:
    def __init__(self) -> None:
        self.accounts: list[dict[str, Any]] = []
        self.fail_login_required = False

    async def create_link_token(self, user_id: uuid.UUID) -> LinkTokenResult:
        return LinkTokenResult(
            link_token="link-x", expiration=datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
        )

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(access_token="access-sandbox-1", item_id="item-sync-1")

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        if self.fail_login_required:
            raise PlaidItemLoginRequiredError(
                "reconnect", error_code="ITEM_LOGIN_REQUIRED", error_type="ITEM_ERROR"
            )
        return AccountsSnapshot(
            accounts=self.accounts,
            item={"item_id": "item-sync-1", "institution_id": "ins_1",
                  "institution_name": "Test Bank"},
        )


async def test_account_sync_flow():
    fake_plaid = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake_plaid
    app.dependency_overrides[get_token_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    user_id: str | None = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, user_id = await register_user(client)
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"public_token": "public-1"},
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            item_id = resp.json()["id"]

            # first sync: checking + savings + credit stored, loan skipped
            fake_plaid.accounts = [
                account("chk-1", "Chase Checking", "depository", "checking", 1500.25, 1400.00),
                account("sav-1", "Chase Savings", "depository", "savings", 8000.00),
                account("cc-1", "Freedom Card", "credit", "credit card", 432.10),
                account("loan-1", "Mortgage", "loan", "mortgage", 250000.00),
            ]
            resp = await client.post(
                "/api/v1/plaid/accounts/sync", json={}, headers=headers
            )
            assert resp.status_code == 200, resp.text
            summary = resp.json()["items"][0]
            assert summary["created"] == 3
            assert summary["updated"] == 0
            assert summary["skipped"] == 1
            assert {a["account_type"] for a in summary["accounts"]} == {"depository", "credit"}

            # second sync, nothing changed: no duplicates, no updates
            resp = await client.post(
                "/api/v1/plaid/accounts/sync",
                json={"item_id": item_id},
                headers=headers,
            )
            summary = resp.json()["items"][0]
            assert summary["created"] == 0
            assert summary["updated"] == 0
            assert len(summary["accounts"]) == 3

            # rename + balance change: updated in place
            fake_plaid.accounts[0] = account(
                "chk-1", "Chase Total Checking", "depository", "checking", 1234.56, 1200.00
            )
            resp = await client.post(
                "/api/v1/plaid/accounts/sync", json={}, headers=headers
            )
            summary = resp.json()["items"][0]
            assert summary["created"] == 0
            assert summary["updated"] == 1
            renamed = next(a for a in summary["accounts"] if a["plaid_account_id"] == "chk-1")
            assert renamed["name"] == "Chase Total Checking"
            assert renamed["current_balance"] == "1234.56"

            # no token → 401; item not owned → 404
            resp = await client.post(
                "/api/v1/plaid/accounts/sync", json={}
            )
            assert resp.status_code == 401
            resp = await client.post(
                "/api/v1/plaid/accounts/sync",
                json={"item_id": str(uuid.uuid4())},
                headers=headers,
            )
            assert resp.status_code == 404

            # Plaid demands re-auth: 409 and the item is flagged in the DB
            fake_plaid.fail_login_required = True
            resp = await client.post(
                "/api/v1/plaid/accounts/sync", json={}, headers=headers
            )
            assert resp.status_code == 409
            assert resp.json()["plaid_error_code"] == "ITEM_LOGIN_REQUIRED"

        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            result = await session.execute(
                select(PlaidItem).where(PlaidItem.plaid_item_id == "item-sync-1")
            )
            assert result.scalar_one().status == "login_required"

            user = await session.get(User, uuid.UUID(user_id))
            await session.delete(user)  # cascades items + accounts
            await session.commit()
    finally:
        app.dependency_overrides.clear()
