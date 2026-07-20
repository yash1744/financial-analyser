"""Label tests: CRUD, duplicate-name conflicts, transaction assignment,
multi-label filtering (OR semantics + no duplicate rows), cascade delete,
and cross-user isolation of both labels and assignment."""

import uuid
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_plaid_service, get_token_cipher
from app.main import app
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
    """Tests write transactions with the placeholder account_id "chk-1";
    both plaid_item_id and the actual account_id are made unique per
    instance here (not derived from public_token, which tests reuse
    across users) so two users seeding in the same test don't collide —
    both are globally unique columns, not scoped per user."""

    def __init__(self, added: list[dict[str, Any]]) -> None:
        self._item_id = f"item-label-{uuid.uuid4().hex[:12]}"
        self._account_id = f"chk-{uuid.uuid4().hex[:12]}"
        self._added = [
            {**txn, "account_id": self._account_id} for txn in added
        ]

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(access_token="access-1", item_id=self._item_id)

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[
                {
                    "account_id": self._account_id,
                    "name": "Checking",
                    "type": "depository",
                    "subtype": "checking",
                    "balances": {"current": 100.0, "available": 90.0,
                                 "iso_currency_code": "USD"},
                },
            ],
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
) -> dict[str, str]:
    """Run a fake sync producing these transactions; return {txn_id: db_id}."""
    fake = FakePlaidService(txns)
    app.dependency_overrides[get_plaid_service] = lambda: fake
    await client.post(
        "/api/v1/plaid/exchange-token", json={"public_token": "1"}, headers=headers
    )
    resp = await client.post("/api/v1/transactions/sync", json={}, headers=headers)
    assert resp.json()["items"][0]["added"] == len(txns)
    resp = await client.get("/api/v1/transactions", headers=headers)
    return {t["plaid_transaction_id"]: t["id"] for t in resp.json()["items"]}


async def test_label_crud_and_duplicate_names():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)

            resp = await client.get("/api/v1/labels", headers=headers)
            assert resp.status_code == 200
            assert resp.json() == []

            resp = await client.post(
                "/api/v1/labels", json={"name": "Vacation"}, headers=headers
            )
            assert resp.status_code == 201, resp.text
            label = resp.json()
            assert label["name"] == "Vacation"
            label_id = label["id"]

            # duplicate name for the same user -> 409
            resp = await client.post(
                "/api/v1/labels", json={"name": "Vacation"}, headers=headers
            )
            assert resp.status_code == 409

            resp = await client.post(
                "/api/v1/labels", json={"name": "Business"}, headers=headers
            )
            assert resp.status_code == 201
            other_label_id = resp.json()["id"]

            # rename to an already-used name -> 409
            resp = await client.patch(
                f"/api/v1/labels/{label_id}",
                json={"name": "Business"},
                headers=headers,
            )
            assert resp.status_code == 409

            # renaming to its own current name is not a false conflict
            resp = await client.patch(
                f"/api/v1/labels/{label_id}",
                json={"name": "Vacation"},
                headers=headers,
            )
            assert resp.status_code == 200

            # actual rename
            resp = await client.patch(
                f"/api/v1/labels/{label_id}",
                json={"name": "Trip"},
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Trip"

            resp = await client.get("/api/v1/labels", headers=headers)
            names = {label["name"] for label in resp.json()}
            assert names == {"Trip", "Business"}

            resp = await client.delete(f"/api/v1/labels/{other_label_id}", headers=headers)
            assert resp.status_code == 204
            resp = await client.get("/api/v1/labels", headers=headers)
            assert [label["name"] for label in resp.json()] == ["Trip"]

            # deleting again -> 404 (already gone)
            resp = await client.delete(f"/api/v1/labels/{other_label_id}", headers=headers)
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_assign_unassign_and_cascade_delete():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            ids = await _seed_transactions(
                client, headers,
                [_txn("l1", "chk-1", 10.0, "Costco", "2026-07-01")],
            )
            txn_id = ids["l1"]

            resp = await client.post(
                "/api/v1/labels", json={"name": "Family"}, headers=headers
            )
            label_id = resp.json()["id"]

            # newly synced transaction has no labels yet
            resp = await client.get(f"/api/v1/transactions/{txn_id}", headers=headers)
            assert resp.json()["labels"] == []

            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/labels/{label_id}", headers=headers
            )
            assert resp.status_code == 200, resp.text
            assert [label["name"] for label in resp.json()["labels"]] == ["Family"]

            # assigning again is a no-op, not a duplicate or an error
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/labels/{label_id}", headers=headers
            )
            assert resp.status_code == 200
            assert len(resp.json()["labels"]) == 1

            # GET /transactions (list) reflects the assignment too
            resp = await client.get("/api/v1/transactions", headers=headers)
            assert [label["name"] for label in resp.json()["items"][0]["labels"]] == ["Family"]

            # unassign
            resp = await client.delete(
                f"/api/v1/transactions/{txn_id}/labels/{label_id}", headers=headers
            )
            assert resp.status_code == 200
            assert resp.json()["labels"] == []

            # unassigning something not assigned is a harmless no-op
            resp = await client.delete(
                f"/api/v1/transactions/{txn_id}/labels/{label_id}", headers=headers
            )
            assert resp.status_code == 200

            # re-assign, then delete the label itself -> cascades off the transaction
            await client.post(
                f"/api/v1/transactions/{txn_id}/labels/{label_id}", headers=headers
            )
            resp = await client.delete(f"/api/v1/labels/{label_id}", headers=headers)
            assert resp.status_code == 204
            resp = await client.get(f"/api/v1/transactions/{txn_id}", headers=headers)
            assert resp.json()["labels"] == []
    finally:
        app.dependency_overrides.clear()


async def test_multi_label_filter_or_semantics_no_duplicates():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            ids = await _seed_transactions(
                client, headers,
                [
                    _txn("m1", "chk-1", 10.0, "Costco", "2026-07-01"),
                    _txn("m2", "chk-1", 20.0, "Whole Foods", "2026-07-02"),
                    _txn("m3", "chk-1", 30.0, "Amazon", "2026-07-03"),
                ],
            )

            family_id = (
                await client.post("/api/v1/labels", json={"name": "Family"}, headers=headers)
            ).json()["id"]
            groceries_id = (
                await client.post("/api/v1/labels", json={"name": "Groceries"}, headers=headers)
            ).json()["id"]

            # m1 gets both labels; m2 gets only groceries; m3 gets neither
            await client.post(
                f"/api/v1/transactions/{ids['m1']}/labels/{family_id}", headers=headers
            )
            await client.post(
                f"/api/v1/transactions/{ids['m1']}/labels/{groceries_id}", headers=headers
            )
            await client.post(
                f"/api/v1/transactions/{ids['m2']}/labels/{groceries_id}", headers=headers
            )

            # single-label filters
            resp = await client.get(
                "/api/v1/transactions", headers=headers,
                params={"label_ids": [family_id]},
            )
            assert [t["plaid_transaction_id"] for t in resp.json()["items"]] == ["m1"]
            assert resp.json()["total"] == 1

            # OR across two labels: m1 (matches both) must appear exactly
            # once, not twice, and the total count must agree
            resp = await client.get(
                "/api/v1/transactions", headers=headers,
                params={"label_ids": [family_id, groceries_id]},
            )
            body = resp.json()
            assert body["total"] == 2
            plaid_ids = [t["plaid_transaction_id"] for t in body["items"]]
            assert sorted(plaid_ids) == ["m1", "m2"]
            assert len(plaid_ids) == len(set(plaid_ids))  # no duplicate row

            # m1's own label list still shows both, independent of the filter
            m1 = next(t for t in body["items"] if t["plaid_transaction_id"] == "m1")
            assert {label["name"] for label in m1["labels"]} == {"Family", "Groceries"}
    finally:
        app.dependency_overrides.clear()


async def test_labels_are_scoped_to_owner():
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            owner_headers, _ = await register_user(client)
            owner_ids = await _seed_transactions(
                client, owner_headers,
                [_txn("s1", "chk-1", 15.0, "Target", "2026-07-01")],
            )
            owner_label_id = (
                await client.post(
                    "/api/v1/labels", json={"name": "Personal"}, headers=owner_headers
                )
            ).json()["id"]

            client.cookies.clear()
            other_headers, _ = await register_user(client)
            other_ids = await _seed_transactions(
                client, other_headers,
                [_txn("s2", "chk-1", 25.0, "Target", "2026-07-02")],
            )

            # other user can't see, rename, or delete the owner's label
            resp = await client.get("/api/v1/labels", headers=other_headers)
            assert resp.json() == []
            resp = await client.patch(
                f"/api/v1/labels/{owner_label_id}",
                json={"name": "Hijacked"},
                headers=other_headers,
            )
            assert resp.status_code == 404
            resp = await client.delete(
                f"/api/v1/labels/{owner_label_id}", headers=other_headers
            )
            assert resp.status_code == 404

            # other user can't assign the owner's label to their own transaction
            resp = await client.post(
                f"/api/v1/transactions/{other_ids['s2']}/labels/{owner_label_id}",
                headers=other_headers,
            )
            assert resp.status_code == 404

            # owner can't assign their label to the other user's transaction either
            resp = await client.post(
                f"/api/v1/transactions/{other_ids['s2']}/labels/{owner_label_id}",
                headers=owner_headers,
            )
            assert resp.status_code == 404

            # unauthenticated is rejected
            resp = await client.get("/api/v1/labels")
            assert resp.status_code == 401

            # sanity: owner's own transaction is unaffected
            resp = await client.get(
                f"/api/v1/transactions/{owner_ids['s1']}", headers=owner_headers
            )
            assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()
