"""ReceiptService: receipt details + images attached to a transaction.

Every operation resolves the transaction through the account→item→user
chain first, so a foreign transaction id behaves exactly like a missing
one (404). Image bytes live in object storage; the database holds only
metadata. Uploads are validated by declared type, size, and magic bytes.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tracing import traced_span
from app.models.receipt import ReceiptImage
from app.models.transaction import Transaction
from app.repositories.receipt import ReceiptRepository
from app.repositories.transaction import TransactionRepository
from app.schemas.receipt import ReceiptDetailsUpdate, ReceiptResponse
from app.services.exceptions import (
    ConflictError,
    InvalidUploadError,
    NotFoundError,
)
from app.services.storage import ObjectNotFoundError, ObjectStorage

logger = logging.getLogger(__name__)

# Allowed upload types with their file extension and magic-byte signature
_IMAGE_TYPES = {
    "image/jpeg": ("jpg", [b"\xff\xd8\xff"]),
    "image/png": ("png", [b"\x89PNG\r\n\x1a\n"]),
    "image/webp": ("webp", [b"RIFF"]),  # + "WEBP" at offset 8, checked below
}


def _validate_image(content_type: str, data: bytes, max_bytes: int) -> None:
    if content_type not in _IMAGE_TYPES:
        allowed = ", ".join(sorted(_IMAGE_TYPES))
        raise InvalidUploadError(f"unsupported image type {content_type!r}; use {allowed}")
    if len(data) == 0:
        raise InvalidUploadError("uploaded file is empty")
    if len(data) > max_bytes:
        raise InvalidUploadError(
            f"image is {len(data)} bytes; the limit is {max_bytes}"
        )
    _, signatures = _IMAGE_TYPES[content_type]
    if not any(data.startswith(s) for s in signatures):
        raise InvalidUploadError("file content does not match its declared image type")
    if content_type == "image/webp" and data[8:12] != b"WEBP":
        raise InvalidUploadError("file content does not match its declared image type")


class ReceiptService:
    def __init__(
        self, session: AsyncSession, storage: ObjectStorage, settings: Settings
    ) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings
        self.transactions = TransactionRepository(session)
        self.receipts = ReceiptRepository(session)

    # --- reads ---

    async def get_receipt(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> ReceiptResponse | None:
        transaction = await self._owned_transaction(user_id, transaction_id)
        receipt = await self.receipts.get_for_transaction(transaction.id)
        return ReceiptResponse.model_validate(receipt) if receipt else None

    async def get_image(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, image_id: uuid.UUID
    ) -> tuple[bytes, ReceiptImage]:
        image = await self._owned_image(user_id, transaction_id, image_id)
        try:
            data = await self.storage.get(image.storage_key)
        except ObjectNotFoundError as exc:
            # metadata without bytes: storage and DB diverged
            logger.error("receipt image %s missing from storage", image.storage_key)
            raise NotFoundError(f"image {image_id} is no longer available") from exc
        return data, image

    # --- writes ---

    async def upsert_details(
        self,
        user_id: uuid.UUID,
        transaction_id: uuid.UUID,
        details: ReceiptDetailsUpdate,
    ) -> ReceiptResponse:
        transaction = await self._owned_transaction(user_id, transaction_id)
        receipt = await self.receipts.get_for_transaction(transaction.id)
        if receipt is None:
            receipt = await self.receipts.create(transaction.id)
        receipt.merchant_name = details.merchant_name
        receipt.receipt_date = details.receipt_date
        receipt.notes = details.notes
        receipt.tax_amount = details.tax_amount
        receipt.tip_amount = details.tip_amount
        receipt.comments = details.comments
        await self.session.commit()
        # re-query so onupdate-driven columns (updated_at) are reloaded;
        # the identity map keeps this the same instance
        refreshed = await self.receipts.get_for_transaction(transaction.id)
        assert refreshed is not None
        return ReceiptResponse.model_validate(refreshed)

    async def delete_receipt(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> None:
        transaction = await self._owned_transaction(user_id, transaction_id)
        receipt = await self.receipts.get_for_transaction(transaction.id)
        if receipt is None:
            raise NotFoundError(f"transaction {transaction_id} has no receipt")
        keys = [image.storage_key for image in receipt.images]
        await self.session.delete(receipt)
        await self.session.commit()
        # storage cleanup after commit: an orphaned object is recoverable
        # noise, a dangling DB row pointing at deleted bytes is a 404 bug
        for key in keys:
            try:
                await self.storage.delete(key)
            except Exception:
                logger.exception("failed to delete receipt object %s", key)

    async def add_image(
        self,
        user_id: uuid.UUID,
        transaction_id: uuid.UUID,
        *,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> ReceiptResponse:
        # No file_name as a span attribute (user-supplied, occasionally
        # carries something sensitive) — content_type/size are enough to
        # diagnose upload issues.
        with traced_span(
            "receipts.add_image",
            {
                "content_type": content_type,
                "size_bytes": len(data),
                "storage_backend": type(self.storage).__name__,
            },
        ):
            transaction = await self._owned_transaction(user_id, transaction_id)
            _validate_image(content_type, data, self.settings.receipt_max_image_bytes)

            receipt = await self.receipts.get_for_transaction(transaction.id)
            if receipt is None:
                receipt = await self.receipts.create(transaction.id)
            if len(receipt.images) >= self.settings.receipt_max_images:
                raise ConflictError(
                    f"a transaction can have at most "
                    f"{self.settings.receipt_max_images} receipt images"
                )

            extension, _ = _IMAGE_TYPES[content_type]
            key = f"receipts/{user_id}/{transaction.id}/{uuid.uuid4().hex}.{extension}"
            await self.storage.put(key, data, content_type)
            try:
                self.receipts.add_image(
                    receipt,
                    storage_key=key,
                    content_type=content_type,
                    file_name=file_name[:255] or f"receipt.{extension}",
                    size_bytes=len(data),
                )
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                try:
                    await self.storage.delete(key)  # don't strand the object
                except Exception:
                    logger.exception("failed to clean up receipt object %s", key)
                raise
            # add_image assigned via the relationship, so receipt.images
            # already holds the new image; the re-query just reloads
            # expired scalars
            refreshed = await self.receipts.get_for_transaction(transaction.id)
            assert refreshed is not None
            return ReceiptResponse.model_validate(refreshed)

    async def delete_image(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, image_id: uuid.UUID
    ) -> None:
        image = await self._owned_image(user_id, transaction_id, image_id)
        key = image.storage_key
        await self.session.delete(image)
        await self.session.commit()
        try:
            await self.storage.delete(key)
        except Exception:
            logger.exception("failed to delete receipt object %s", key)

    # --- internals ---

    async def _owned_transaction(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Transaction:
        transaction = await self.transactions.get_for_user(transaction_id, user_id)
        if transaction is None:
            raise NotFoundError(f"transaction {transaction_id} does not exist")
        return transaction

    async def _owned_image(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, image_id: uuid.UUID
    ) -> ReceiptImage:
        transaction = await self._owned_transaction(user_id, transaction_id)
        receipt = await self.receipts.get_for_transaction(transaction.id)
        image = (
            await self.receipts.get_image(receipt.id, image_id) if receipt else None
        )
        if image is None:
            raise NotFoundError(f"image {image_id} does not exist")
        return image
