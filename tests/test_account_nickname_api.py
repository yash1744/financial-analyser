"""Account nickname tests: set/edit/clear, display-name fallback,
survival across a Plaid re-sync, and cross-user isolation."""

import uuid
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_plaid_service, get_token_cipher
from app.main import app
from app.schemas.plaid import (
    AccountsSnapshot,
    ExchangedPublicToken,
    TransactionsSyncResult,
)
from app.utils.crypto import TokenCipher
from tests.conftest import register_user


class FakePlaidService:
    """Serves one account whose Plaid name we can flip to simulate a
    re-sync renaming it."""

    def __init__(self) -> None:
        self.account_name = "Plaid Checking"

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(
            access_token="access-1", item_id=f"item-nick-{public_token}"
        )

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[
                {
                    "account_id": "chk-1",
                    "name": self.account_name,
                    "type": "depository",
                    "subtype": "checking",
                    "balances": {
                        "current": 100.0,
                        "available": 90.0,
                        "iso_currency_code": "USD",
                    },
                },
            ],
            item={
                "item_id": "item-nick-1",
                "institution_id": "ins_1",
                "institution_name": "Test Bank",
            },
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        return TransactionsSyncResult(
            added=[], modified=[], removed=[], next_cursor="cur-1"
        )


async def _connect_and_get_account(
    client: AsyncClient, headers: dict[str, Any]
) -> dict[str, Any]:
    await client.post(
        "/api/v1/plaid/exchange-token", json={"public_token": "1"}, headers=headers
    )
    resp = await client.post("/api/v1/plaid/accounts/sync", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.get("/api/v1/accounts", headers=headers)
    return resp.json()[0]


async def test_nickname_set_edit_clear_and_display_name():
    fake = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            account = await _connect_and_get_account(client, headers)
            account_id = account["id"]

            # no nickname → display falls back to the Plaid name
            assert account["nickname"] is None
            assert account["name"] == "Plaid Checking"
            assert account["display_name"] == "Plaid Checking"

            # set a nickname
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "Daily Spending"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["nickname"] == "Daily Spending"
            assert body["name"] == "Plaid Checking"  # original preserved
            assert body["display_name"] == "Daily Spending"

            # it persists on the list endpoint
            resp = await client.get("/api/v1/accounts", headers=headers)
            assert resp.json()[0]["display_name"] == "Daily Spending"

            # edit it (and confirm surrounding whitespace is trimmed)
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "  Emergency Fund  "},
                headers=headers,
            )
            assert resp.json()["nickname"] == "Emergency Fund"

            # clear via explicit null → reverts to the Plaid name
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": None},
                headers=headers,
            )
            assert resp.json()["nickname"] is None
            assert resp.json()["display_name"] == "Plaid Checking"

            # a blank string also clears it
            await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "Temp"},
                headers=headers,
            )
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "   "},
                headers=headers,
            )
            assert resp.json()["nickname"] is None

            # over-long nicknames are rejected
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "x" * 101},
                headers=headers,
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_nickname_survives_resync():
    fake = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            account = await _connect_and_get_account(client, headers)
            account_id = account["id"]

            await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "My Checking"},
                headers=headers,
            )

            # Plaid renames the account and we re-sync
            fake.account_name = "Plaid Checking (Renamed)"
            resp = await client.post(
                "/api/v1/plaid/accounts/sync", json={}, headers=headers
            )
            assert resp.status_code == 200

            resp = await client.get("/api/v1/accounts", headers=headers)
            account = resp.json()[0]
            # the Plaid name updated, but the nickname (and display) stuck
            assert account["name"] == "Plaid Checking (Renamed)"
            assert account["nickname"] == "My Checking"
            assert account["display_name"] == "My Checking"
    finally:
        app.dependency_overrides.clear()


async def test_nickname_scoped_to_owner():
    fake = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            owner_headers, _ = await register_user(client)
            account = await _connect_and_get_account(client, owner_headers)
            account_id = account["id"]

            client.cookies.clear()
            other_headers, _ = await register_user(client)
            # a foreign account id is a 404, not a 403 (existence not leaked)
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}",
                json={"nickname": "hijack"},
                headers=other_headers,
            )
            assert resp.status_code == 404

            # unknown id → 404; unauthenticated → 401
            resp = await client.patch(
                f"/api/v1/accounts/{uuid.uuid4()}",
                json={"nickname": "x"},
                headers=other_headers,
            )
            assert resp.status_code == 404
            resp = await client.patch(
                f"/api/v1/accounts/{account_id}", json={"nickname": "x"}
            )
            assert resp.status_code == 401

            # the owner's nickname was never touched
            resp = await client.get("/api/v1/accounts", headers=owner_headers)
            assert resp.json()[0]["nickname"] is None
    finally:
        app.dependency_overrides.clear()
