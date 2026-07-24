"""Receipt attachment tests: details CRUD, image/PDF upload/serve/delete,
the per-transaction attachment cap, upload validation, and cross-user
isolation (a foreign transaction id is indistinguishable from a missing
one)."""

import tempfile
from decimal import Decimal
from typing import Any

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_object_storage,
    get_plaid_service,
    get_settings,
    get_token_cipher,
)
from app.main import app
from app.schemas.plaid import (
    AccountsSnapshot,
    ExchangedPublicToken,
    TransactionsSyncResult,
)
from app.services.storage import LocalObjectStorage
from app.utils.crypto import TokenCipher
from tests.conftest import register_user

# Minimal payloads that satisfy the magic-byte check in the validator.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64  # unsupported type


def _txn(txn_id: str, account_id: str, amount: float, when: str) -> dict[str, Any]:
    return {
        "transaction_id": txn_id,
        "account_id": account_id,
        "amount": amount,
        "date": when,
        "name": f"Merchant {txn_id}",
        "merchant_name": f"Merchant {txn_id}",
        "iso_currency_code": "USD",
        "pending": False,
    }


class FakePlaidService:
    def __init__(self, added: list[dict[str, Any]]) -> None:
        self._added = added

    async def exchange_public_token(self, public_token: str) -> ExchangedPublicToken:
        return ExchangedPublicToken(
            access_token="access-1", item_id=f"item-receipt-{public_token}"
        )

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        return AccountsSnapshot(
            accounts=[
                {
                    "account_id": "chk-1",
                    "name": "Checking",
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
                "item_id": "item-receipt-1",
                "institution_id": "ins_1",
                "institution_name": "Test Bank",
            },
        )

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> TransactionsSyncResult:
        return TransactionsSyncResult(
            added=self._added, modified=[], removed=[], next_cursor="cur-1"
        )


async def _seed_transaction(client: AsyncClient, headers: dict[str, str]) -> str:
    """Run a fake sync producing one transaction; return its id."""
    await client.post(
        "/api/v1/plaid/exchange-token", json={"public_token": "1"}, headers=headers
    )
    resp = await client.post("/api/v1/transactions/sync", json={}, headers=headers)
    assert resp.json()["items"][0]["added"] >= 1
    resp = await client.get("/api/v1/transactions", headers=headers)
    return resp.json()["items"][0]["id"]


def _use_temp_storage() -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    app.dependency_overrides[get_object_storage] = lambda: LocalObjectStorage(tmp.name)
    return tmp


async def test_receipt_details_and_image_lifecycle():
    fake = FakePlaidService([_txn("r1", "chk-1", 12.50, "2026-07-01")])
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    tmp = _use_temp_storage()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            txn_id = await _seed_transaction(client, headers)

            # no receipt yet
            resp = await client.get(
                f"/api/v1/transactions/{txn_id}/receipt", headers=headers
            )
            assert resp.status_code == 200
            assert resp.json() is None

            # set details (creates the receipt)
            resp = await client.put(
                f"/api/v1/transactions/{txn_id}/receipt",
                json={
                    "merchant_name": "Corner Store",
                    "receipt_date": "2026-07-01",
                    "notes": "team lunch",
                    "tax_amount": "1.10",
                    "tip_amount": "2.00",
                },
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["merchant_name"] == "Corner Store"
            assert Decimal(body["tax_amount"]) == Decimal("1.10")
            assert body["images"] == []

            # upload an image
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("lunch.png", PNG, "image/png")},
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert len(body["images"]) == 1
            image = body["images"][0]
            assert image["file_name"] == "lunch.png"
            assert image["content_type"] == "image/png"
            assert image["size_bytes"] == len(PNG)
            # details survived the image upload
            assert body["merchant_name"] == "Corner Store"
            image_id = image["id"]

            # fetch the raw bytes back
            resp = await client.get(
                f"/api/v1/transactions/{txn_id}/receipt/images/{image_id}",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/png"
            assert resp.content == PNG

            # a second image of a different type is fine
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("scan.webp", WEBP, "image/webp")},
                headers=headers,
            )
            assert resp.status_code == 201
            assert len(resp.json()["images"]) == 2

            # a PDF attaches alongside the images, not as a separate concept
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("invoice.pdf", PDF, "application/pdf")},
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert len(body["images"]) == 3
            pdf_attachment = next(i for i in body["images"] if i["file_name"] == "invoice.pdf")
            assert pdf_attachment["content_type"] == "application/pdf"
            assert pdf_attachment["size_bytes"] == len(PDF)
            pdf_id = pdf_attachment["id"]

            # fetch it back: correct media type, inline disposition (so the
            # browser's native PDF viewer can render it rather than forcing
            # a download)
            resp = await client.get(
                f"/api/v1/transactions/{txn_id}/receipt/images/{pdf_id}",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            assert 'inline; filename="invoice.pdf"' in resp.headers["content-disposition"]
            assert resp.content == PDF

            # delete the first image
            resp = await client.delete(
                f"/api/v1/transactions/{txn_id}/receipt/images/{image_id}",
                headers=headers,
            )
            assert resp.status_code == 204
            resp = await client.get(
                f"/api/v1/transactions/{txn_id}/receipt", headers=headers
            )
            assert len(resp.json()["images"]) == 2  # webp + pdf remain
            # its bytes are gone
            resp = await client.get(
                f"/api/v1/transactions/{txn_id}/receipt/images/{image_id}",
                headers=headers,
            )
            assert resp.status_code == 404

            # clearing a field via PUT (full replacement) drops it
            resp = await client.put(
                f"/api/v1/transactions/{txn_id}/receipt",
                json={"merchant_name": "Renamed"},
                headers=headers,
            )
            assert resp.json()["notes"] is None
            assert resp.json()["merchant_name"] == "Renamed"

            # delete the whole receipt
            resp = await client.delete(
                f"/api/v1/transactions/{txn_id}/receipt", headers=headers
            )
            assert resp.status_code == 204
            resp = await client.get(
                f"/api/v1/transactions/{txn_id}/receipt", headers=headers
            )
            assert resp.json() is None
    finally:
        app.dependency_overrides.clear()
        tmp.cleanup()


async def test_upload_validation_and_image_cap():
    fake = FakePlaidService([_txn("r2", "chk-1", 5.00, "2026-07-02")])
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    tmp = _use_temp_storage()
    # shrink the cap so the test stays small
    settings = get_settings()
    original_max = settings.receipt_max_images
    settings.receipt_max_images = 2
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers, _ = await register_user(client)
            txn_id = await _seed_transaction(client, headers)

            # unsupported type → 400
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("anim.gif", GIF, "image/gif")},
                headers=headers,
            )
            assert resp.status_code == 400

            # declared png but bytes aren't → 400 (magic-byte mismatch)
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("fake.png", b"not a real image", "image/png")},
                headers=headers,
            )
            assert resp.status_code == 400

            # declared PDF but bytes aren't → 400, same magic-byte check
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("fake.pdf", b"not a real pdf", "application/pdf")},
                headers=headers,
            )
            assert resp.status_code == 400

            # fill to the cap — a mix of an image and a PDF, since the cap
            # counts all attachments together, not images alone
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("ok.png", PNG, "image/png")},
                headers=headers,
            )
            assert resp.status_code == 201
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("ok.pdf", PDF, "application/pdf")},
                headers=headers,
            )
            assert resp.status_code == 201
            # one more (of either type) → 409
            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("over.png", PNG, "image/png")},
                headers=headers,
            )
            assert resp.status_code == 409
            assert "attachments" in resp.json()["detail"]
    finally:
        settings.receipt_max_images = original_max
        app.dependency_overrides.clear()
        tmp.cleanup()


async def test_receipts_are_scoped_to_owner():
    fake = FakePlaidService([_txn("r3", "chk-1", 8.00, "2026-07-03")])
    cipher = TokenCipher(Fernet.generate_key().decode())
    app.dependency_overrides[get_plaid_service] = lambda: fake
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    tmp = _use_temp_storage()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            owner_headers, _ = await register_user(client)
            txn_id = await _seed_transaction(client, owner_headers)
            await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("r.png", PNG, "image/png")},
                headers=owner_headers,
            )

            # a different user cannot see or touch that transaction's receipt
            client.cookies.clear()
            other_headers, _ = await register_user(client)
            for method, path in [
                ("GET", f"/api/v1/transactions/{txn_id}/receipt"),
                ("GET", f"/api/v1/transactions/{txn_id}"),
                ("DELETE", f"/api/v1/transactions/{txn_id}/receipt"),
            ]:
                resp = await client.request(method, path, headers=other_headers)
                assert resp.status_code == 404, f"{method} {path} -> {resp.status_code}"

            resp = await client.post(
                f"/api/v1/transactions/{txn_id}/receipt/images",
                files={"file": ("x.png", PNG, "image/png")},
                headers=other_headers,
            )
            assert resp.status_code == 404

            # unauthenticated is rejected too
            resp = await client.get(f"/api/v1/transactions/{txn_id}/receipt")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
        tmp.cleanup()
