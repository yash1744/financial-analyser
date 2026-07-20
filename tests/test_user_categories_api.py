"""User category tests: CRUD, duplicate-name conflicts, mapping Plaid
categories onto a user category (repoint-not-duplicate, cascade delete,
ownership), and the analytics rollup itself (multiple Plaid categories
collapsing into one grouped row when mapped to the same user category)."""

import uuid
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_plaid_service, get_token_cipher
from app.db.session import SessionFactory
from app.main import app
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.plaid import AccountsSnapshot, ExchangedPublicToken, TransactionsSyncResult
from app.utils.crypto import TokenCipher
from tests.conftest import register_user


def _txn(txn_id: str, account_id: str, amount: float, name: str, when: str) -> dict[str, Any]:
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
    """Unique item_id/account_id per instance so multiple users seeding in
    the same test never collide on those globally-unique columns."""

    def __init__(self, added: list[dict[str, Any]]) -> None:
        self._item_id = f"item-usercat-{uuid.uuid4().hex[:12]}"
        self._account_id = f"chk-{uuid.uuid4().hex[:12]}"
        self._added = [{**txn, "account_id": self._account_id} for txn in added]

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(access_token="access-1", item_id=self._item_id)

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[{
                "account_id": self._account_id, "name": "Checking",
                "type": "depository", "subtype": "checking",
                "balances": {"current": 100.0, "available": 90.0, "iso_currency_code": "USD"},
            }],
            item={"item_id": self._item_id, "institution_id": "ins_1",
                  "institution_name": "Test Bank"},
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        return TransactionsSyncResult(
            added=self._added, modified=[], removed=[], next_cursor="cur-1"
        )


async def _seed_transactions(
    client: AsyncClient, headers: dict[str, str], txns: list[dict[str, Any]]
) -> None:
    fake = FakePlaidService(txns)
    app.dependency_overrides[get_plaid_service] = lambda: fake
    await client.post(
        "/api/v1/plaid/exchange-token", json={"public_token": "1"}, headers=headers
    )
    resp = await client.post("/api/v1/transactions/sync", json={}, headers=headers)
    assert resp.json()["items"][0]["added"] == len(txns)


async def _make_category(name_prefix: str) -> uuid.UUID:
    """Categories are only ever created by Plaid auto-categorization in the
    app itself; tests insert directly, same as test_analytics_api.py."""
    async with SessionFactory() as session:
        category = Category(name=f"{name_prefix}-{uuid.uuid4().hex[:6]}")
        session.add(category)
        await session.flush()
        category_id = category.id
        await session.commit()
        return category_id


async def _categorize(plaid_transaction_id: str, category_id: uuid.UUID) -> None:
    from sqlalchemy import select

    async with SessionFactory() as session:
        transaction = (
            await session.execute(
                select(Transaction).where(
                    Transaction.plaid_transaction_id == plaid_transaction_id
                )
            )
        ).scalar_one()
        transaction.category_id = category_id
        await session.commit()


async def test_user_category_crud_and_duplicate_names():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)

            resp = await client.get("/api/v1/user-categories", headers=headers)
            assert resp.status_code == 200
            assert resp.json() == []

            resp = await client.post(
                "/api/v1/user-categories", json={"name": "Dining Out"}, headers=headers
            )
            assert resp.status_code == 201, resp.text
            dining_id = resp.json()["id"]

            resp = await client.post(
                "/api/v1/user-categories", json={"name": "Dining Out"}, headers=headers
            )
            assert resp.status_code == 409

            resp = await client.post(
                "/api/v1/user-categories", json={"name": "Fixed Costs"}, headers=headers
            )
            assert resp.status_code == 201
            fixed_id = resp.json()["id"]

            # rename to an already-used name -> 409
            resp = await client.patch(
                f"/api/v1/user-categories/{dining_id}",
                json={"name": "Fixed Costs"}, headers=headers,
            )
            assert resp.status_code == 409

            # renaming to its own current name is not a false conflict
            resp = await client.patch(
                f"/api/v1/user-categories/{dining_id}",
                json={"name": "Dining Out"}, headers=headers,
            )
            assert resp.status_code == 200

            resp = await client.patch(
                f"/api/v1/user-categories/{dining_id}",
                json={"name": "Eating Out"}, headers=headers,
            )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Eating Out"

            resp = await client.delete(f"/api/v1/user-categories/{fixed_id}", headers=headers)
            assert resp.status_code == 204
            resp = await client.get("/api/v1/user-categories", headers=headers)
            assert [c["name"] for c in resp.json()] == ["Eating Out"]

            resp = await client.delete(f"/api/v1/user-categories/{fixed_id}", headers=headers)
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_mapping_repoints_instead_of_duplicating():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    restaurants_id = fast_food_id = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            dining_id = (
                await client.post(
                    "/api/v1/user-categories", json={"name": "Dining Out"}, headers=headers
                )
            ).json()["id"]
            other_id = (
                await client.post(
                    "/api/v1/user-categories", json={"name": "Something Else"}, headers=headers
                )
            ).json()["id"]

            restaurants_id = await _make_category("Restaurants")
            fast_food_id = await _make_category("Fast Food")

            resp = await client.put(
                f"/api/v1/user-categories/mappings/{restaurants_id}",
                json={"user_category_id": dining_id}, headers=headers,
            )
            assert resp.status_code == 200, resp.text
            resp = await client.put(
                f"/api/v1/user-categories/mappings/{fast_food_id}",
                json={"user_category_id": dining_id}, headers=headers,
            )
            assert resp.status_code == 200

            resp = await client.get("/api/v1/user-categories/mappings", headers=headers)
            assert len(resp.json()) == 2

            # repoint restaurants -> a different user category; must not
            # create a second row for the same (user, category)
            resp = await client.put(
                f"/api/v1/user-categories/mappings/{restaurants_id}",
                json={"user_category_id": other_id}, headers=headers,
            )
            assert resp.status_code == 200
            resp = await client.get("/api/v1/user-categories/mappings", headers=headers)
            mappings = resp.json()
            assert len(mappings) == 2
            restaurants_mapping = next(
                m for m in mappings if m["category_id"] == str(restaurants_id)
            )
            assert restaurants_mapping["user_category_id"] == other_id

            resp = await client.delete(
                f"/api/v1/user-categories/mappings/{fast_food_id}", headers=headers
            )
            assert resp.status_code == 204
            resp = await client.get("/api/v1/user-categories/mappings", headers=headers)
            assert len(resp.json()) == 1

            # unmapping something already unmapped is a harmless no-op
            resp = await client.delete(
                f"/api/v1/user-categories/mappings/{fast_food_id}", headers=headers
            )
            assert resp.status_code == 204

            # mapping a Plaid category that doesn't exist -> 404
            resp = await client.put(
                f"/api/v1/user-categories/mappings/{uuid.uuid4()}",
                json={"user_category_id": dining_id}, headers=headers,
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        async with SessionFactory() as session:
            for cid in (restaurants_id, fast_food_id):
                if cid is not None:
                    category = await session.get(Category, cid)
                    if category is not None:
                        await session.delete(category)
            await session.commit()


async def test_category_breakdown_resolves_through_mapping():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    restaurants_id = fast_food_id = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            await _seed_transactions(client, headers, [
                _txn("uc1", "chk-1", 10.00, "Chez Restaurant", "2026-07-01"),
                _txn("uc2", "chk-1", 20.00, "Burger Place", "2026-07-02"),
                _txn("uc3", "chk-1", 5.00, "Corner Store", "2026-07-03"),  # stays uncategorized
            ])

            restaurants_id = await _make_category("Restaurants")
            fast_food_id = await _make_category("Fast Food")
            await _categorize("uc1", restaurants_id)
            await _categorize("uc2", fast_food_id)

            dining_id = (
                await client.post(
                    "/api/v1/user-categories", json={"name": "Dining Out"}, headers=headers
                )
            ).json()["id"]
            await client.put(
                f"/api/v1/user-categories/mappings/{restaurants_id}",
                json={"user_category_id": dining_id}, headers=headers,
            )
            await client.put(
                f"/api/v1/user-categories/mappings/{fast_food_id}",
                json={"user_category_id": dining_id}, headers=headers,
            )

            resp = await client.get("/api/v1/analytics/category-breakdown", headers=headers)
            body = resp.json()
            assert body["total_spending"] == "35.00"
            by_name = {c["category_name"]: c for c in body["categories"]}
            assert set(by_name) == {"Dining Out", "Uncategorized"}
            dining = by_name["Dining Out"]
            assert dining["category_id"] == dining_id
            assert dining["is_custom"] is True
            assert (dining["total"], dining["transaction_count"]) == ("30.00", 2)
            uncategorized = by_name["Uncategorized"]
            assert uncategorized["category_id"] is None
            assert uncategorized["is_custom"] is False
            assert uncategorized["total"] == "5.00"

            # unmap fast food -> it reappears under its own raw name
            resp = await client.delete(
                f"/api/v1/user-categories/mappings/{fast_food_id}", headers=headers
            )
            assert resp.status_code == 204
            resp = await client.get("/api/v1/analytics/category-breakdown", headers=headers)
            categories = resp.json()["categories"]
            assert len(categories) == 3  # Dining Out, raw Fast Food, Uncategorized
            by_id = {c["category_id"]: c for c in categories}
            fast_food_row = by_id[str(fast_food_id)]
            assert fast_food_row["is_custom"] is False
            assert fast_food_row["total"] == "20.00"
            dining_row = by_id[dining_id]
            assert dining_row["is_custom"] is True
            assert dining_row["total"] == "10.00"  # restaurants only now

            # deleting the user category cascades the remaining mapping —
            # restaurants also reverts to its raw name
            resp = await client.delete(f"/api/v1/user-categories/{dining_id}", headers=headers)
            assert resp.status_code == 204
            resp = await client.get("/api/v1/analytics/category-breakdown", headers=headers)
            names = {c["category_name"] for c in resp.json()["categories"]}
            assert "Dining Out" not in names
    finally:
        app.dependency_overrides.clear()
        async with SessionFactory() as session:
            for cid in (restaurants_id, fast_food_id):
                if cid is not None:
                    category = await session.get(Category, cid)
                    if category is not None:
                        await session.delete(category)
            await session.commit()


async def test_user_categories_scoped_to_owner():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    shared_category_id = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            owner_headers, _ = await register_user(client)
            owner_category_id = (
                await client.post(
                    "/api/v1/user-categories", json={"name": "Personal"}, headers=owner_headers
                )
            ).json()["id"]

            client.cookies.clear()
            other_headers, _ = await register_user(client)

            shared_category_id = await _make_category("Shared Plaid Category")

            # other user can't see, rename, or delete the owner's category
            resp = await client.get("/api/v1/user-categories", headers=other_headers)
            assert resp.json() == []
            resp = await client.patch(
                f"/api/v1/user-categories/{owner_category_id}",
                json={"name": "Hijacked"}, headers=other_headers,
            )
            assert resp.status_code == 404
            resp = await client.delete(
                f"/api/v1/user-categories/{owner_category_id}", headers=other_headers
            )
            assert resp.status_code == 404

            # other user can't map using the owner's user_category_id
            resp = await client.put(
                f"/api/v1/user-categories/mappings/{shared_category_id}",
                json={"user_category_id": owner_category_id}, headers=other_headers,
            )
            assert resp.status_code == 404

            # owner maps the shared Plaid category
            resp = await client.put(
                f"/api/v1/user-categories/mappings/{shared_category_id}",
                json={"user_category_id": owner_category_id}, headers=owner_headers,
            )
            assert resp.status_code == 200

            # the same Plaid category, mapped independently by the other
            # user to their own category — must not conflict with the
            # owner's mapping (the mapping is per-user, not global)
            other_category_id = (
                await client.post(
                    "/api/v1/user-categories", json={"name": "Also Personal"},
                    headers=other_headers,
                )
            ).json()["id"]
            resp = await client.put(
                f"/api/v1/user-categories/mappings/{shared_category_id}",
                json={"user_category_id": other_category_id}, headers=other_headers,
            )
            assert resp.status_code == 200

            owner_mappings = (
                await client.get("/api/v1/user-categories/mappings", headers=owner_headers)
            ).json()
            other_mappings = (
                await client.get("/api/v1/user-categories/mappings", headers=other_headers)
            ).json()
            assert owner_mappings[0]["user_category_id"] == owner_category_id
            assert other_mappings[0]["user_category_id"] == other_category_id

            resp = await client.get("/api/v1/user-categories")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
        if shared_category_id is not None:
            async with SessionFactory() as session:
                category = await session.get(Category, shared_category_id)
                if category is not None:
                    await session.delete(category)
                await session.commit()
