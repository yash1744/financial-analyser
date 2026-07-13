"""Integration tests for the Link flow: real Postgres, fake Plaid API.

Kept as one test function so the whole flow shares one event loop
(the async engine's pooled connections are loop-bound).
"""

import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_plaid_service, get_token_cipher
from app.main import app
from app.models.plaid_item import PlaidItem
from app.models.user import User
from app.schemas.plaid import AccountsSnapshot, ExchangedPublicToken, LinkTokenResult
from app.utils.crypto import TokenCipher


class FakePlaidService:
    """Stands in for the Plaid gateway; returns canned sandbox-shaped data."""

    def __init__(self) -> None:
        self.exchange_calls: list[str] = []

    async def create_link_token(self, user_id: uuid.UUID) -> LinkTokenResult:
        return LinkTokenResult(
            link_token=f"link-sandbox-{user_id}",
            expiration=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        )

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        self.exchange_calls.append(public_token)
        return ExchangedPublicToken(
            access_token=f"access-sandbox-{public_token}", item_id="item-fake-1"
        )

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[{"account_id": "a1", "name": "Checking"}],
            item={"item_id": "item-fake-1", "institution_id": "ins_109508",
                  "institution_name": "First Platypus Bank"},
        )


async def test_full_link_flow():
    fake_plaid = FakePlaidService()
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake_plaid
    app.dependency_overrides[get_token_cipher] = lambda: cipher

    email = f"link-flow-{uuid.uuid4().hex[:12]}@example.com"
    transport = ASGITransport(app=app)
    created_user_ids: list[str] = []
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # create a user to link against
            resp = await client.post("/api/v1/users", json={"email": email})
            assert resp.status_code == 201, resp.text
            user_id = resp.json()["id"]
            created_user_ids.append(user_id)

            # duplicate email is rejected
            resp = await client.post("/api/v1/users", json={"email": email.upper()})
            assert resp.status_code == 409

            # invalid email is rejected by schema validation
            resp = await client.post("/api/v1/users", json={"email": "not-an-email"})
            assert resp.status_code == 422

            # step 1: link token
            resp = await client.post("/api/v1/plaid/link-token", json={"user_id": user_id})
            assert resp.status_code == 200, resp.text
            assert resp.json()["link_token"].startswith("link-sandbox-")

            # link token for a nonexistent user → 404
            resp = await client.post(
                "/api/v1/plaid/link-token", json={"user_id": str(uuid.uuid4())}
            )
            assert resp.status_code == 404

            # empty public_token fails validation
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": ""},
            )
            assert resp.status_code == 422

            # step 2: exchange and persist
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-sandbox-123"},
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["plaid_item_id"] == "item-fake-1"
            assert body["institution_name"] == "First Platypus Bank"
            assert body["status"] == "active"
            assert "access_token" not in body

            # re-linking the same item for the same user updates in place
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-sandbox-456"},
            )
            assert resp.status_code == 201
            assert resp.json()["id"] == body["id"]

            # the same item claimed by a different user → 409
            resp = await client.post(
                "/api/v1/users", json={"email": f"other-{uuid.uuid4().hex[:12]}@example.com"}
            )
            other_user_id = resp.json()["id"]
            created_user_ids.append(other_user_id)
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": other_user_id, "public_token": "public-sandbox-789"},
            )
            assert resp.status_code == 409

        # the stored token is ciphertext that decrypts to the latest exchange
        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            result = await session.execute(
                select(PlaidItem).where(PlaidItem.plaid_item_id == "item-fake-1")
            )
            item = result.scalar_one()
            stored = item.access_token_encrypted
            assert stored != "access-sandbox-public-sandbox-456"
            assert cipher.decrypt(stored) == "access-sandbox-public-sandbox-456"

            # cleanup: deleting users cascades to items
            for uid in created_user_ids:
                user = await session.get(User, uuid.UUID(uid))
                await session.delete(user)
            await session.commit()
    finally:
        app.dependency_overrides.clear()
