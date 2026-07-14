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
    """Stands in for the Plaid gateway; returns canned sandbox-shaped data.

    `next_item_id` / `institution` are mutable so tests can simulate what
    Plaid actually does: a fresh Link session mints a NEW item_id even for
    an institution the user already connected.
    """

    def __init__(self) -> None:
        self.exchange_calls: list[str] = []
        self.removed_tokens: list[str] = []
        self.remove_raises = False
        self.next_item_id = "item-fake-1"
        self.institution = ("ins_109508", "First Platypus Bank")

    async def create_link_token(self, user_id: uuid.UUID) -> LinkTokenResult:
        return LinkTokenResult(
            link_token=f"link-sandbox-{user_id}",
            expiration=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        )

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        self.exchange_calls.append(public_token)
        return ExchangedPublicToken(
            access_token=f"access-sandbox-{public_token}", item_id=self.next_item_id
        )

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        institution_id, institution_name = self.institution
        return AccountsSnapshot(
            accounts=[{"account_id": "a1", "name": "Checking"}],
            item={"item_id": self.next_item_id, "institution_id": institution_id,
                  "institution_name": institution_name},
        )

    async def remove_item(self, access_token: str) -> None:
        self.removed_tokens.append(access_token)
        if self.remove_raises:
            raise RuntimeError("plaid is down")


async def test_duplicate_institution_link():
    """A fresh Link session for an already-connected bank (new item_id,
    same institution) must not create a duplicate connection."""
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
                json={"email": f"dup-link-{uuid.uuid4().hex[:12]}@example.com"},
            )
            user_id = resp.json()["id"]

            fake_plaid.next_item_id = "item-dup-1"
            fake_plaid.institution = ("ins_dup", "Duplicate Bank")
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-1"},
            )
            assert resp.status_code == 201
            first_item_id = resp.json()["id"]

            # same bank again, but Plaid mints a new item_id → rejected,
            # even when releasing the orphan item at Plaid fails
            fake_plaid.next_item_id = "item-dup-2"
            fake_plaid.remove_raises = True
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-2"},
            )
            assert resp.status_code == 409
            assert "Duplicate Bank is already connected" in resp.json()["detail"]
            assert fake_plaid.removed_tokens == ["access-sandbox-public-2"]

            # a different institution is fine
            fake_plaid.next_item_id = "item-dup-3"
            fake_plaid.institution = ("ins_other", "Other Bank")
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-3"},
            )
            assert resp.status_code == 201

        from app.db.session import SessionFactory
        from app.models.enums import PlaidItemStatus

        async with SessionFactory() as session:
            items = list(
                (
                    await session.execute(
                        select(PlaidItem).where(PlaidItem.user_id == uuid.UUID(user_id))
                    )
                ).scalars()
            )
            # no duplicate row was created
            assert sorted(i.plaid_item_id for i in items) == ["item-dup-1", "item-dup-3"]

            # broken connection: a fresh link is the recovery path — the
            # stale item is retired, the new one connects
            first = next(i for i in items if str(i.id) == first_item_id)
            first.status = PlaidItemStatus.LOGIN_REQUIRED
            await session.commit()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake_plaid.next_item_id = "item-dup-4"
            fake_plaid.institution = ("ins_dup", "Duplicate Bank")
            resp = await client.post(
                "/api/v1/plaid/exchange-token",
                json={"user_id": user_id, "public_token": "public-4"},
            )
            assert resp.status_code == 201
            assert resp.json()["status"] == "active"

        async with SessionFactory() as session:
            items = {
                i.plaid_item_id: i
                for i in (
                    await session.execute(
                        select(PlaidItem).where(PlaidItem.user_id == uuid.UUID(user_id))
                    )
                ).scalars()
            }
            assert items["item-dup-1"].status == PlaidItemStatus.DISCONNECTED
            assert items["item-dup-4"].status == PlaidItemStatus.ACTIVE

            user = await session.get(User, uuid.UUID(user_id))
            await session.delete(user)
            await session.commit()
    finally:
        app.dependency_overrides.clear()


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
