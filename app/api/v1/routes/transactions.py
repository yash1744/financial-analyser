import uuid
from typing import Annotated

from fastapi import APIRouter, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import (
    CurrentUserDep,
    LabelServiceDep,
    ReceiptServiceDep,
    TransactionQueryServiceDep,
    TransactionSyncServiceDep,
)
from app.schemas.receipt import ReceiptDetailsUpdate, ReceiptResponse
from app.schemas.transaction import (
    PaginatedTransactionsResponse,
    TransactionListQuery,
    TransactionResponse,
    TransactionsSyncApiRequest,
    TransactionsSyncApiResponse,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=PaginatedTransactionsResponse)
async def list_transactions(
    query: Annotated[TransactionListQuery, Query()],
    user: CurrentUserDep,
    service: TransactionQueryServiceDep,
) -> PaginatedTransactionsResponse:
    """Filterable, sortable, paginated view of the user's transactions."""
    return await service.list_transactions(user.id, query)


@router.post("/sync", response_model=TransactionsSyncApiResponse)
async def sync_transactions(
    body: TransactionsSyncApiRequest,
    user: CurrentUserDep,
    service: TransactionSyncServiceDep,
) -> TransactionsSyncApiResponse:
    """Pull transaction changes from Plaid via cursor-based /transactions/sync."""
    summaries = await service.sync_transactions(user.id, body.item_id)
    return TransactionsSyncApiResponse(items=summaries)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    user: CurrentUserDep,
    service: TransactionQueryServiceDep,
) -> TransactionResponse:
    return await service.get_transaction(user.id, transaction_id)


# --- receipts ---


@router.get("/{transaction_id}/receipt", response_model=ReceiptResponse | None)
async def get_receipt(
    transaction_id: uuid.UUID,
    user: CurrentUserDep,
    service: ReceiptServiceDep,
) -> ReceiptResponse | None:
    """The transaction's receipt (details + image metadata), or null when
    none has been attached yet."""
    return await service.get_receipt(user.id, transaction_id)


@router.put("/{transaction_id}/receipt", response_model=ReceiptResponse)
async def put_receipt_details(
    transaction_id: uuid.UUID,
    body: ReceiptDetailsUpdate,
    user: CurrentUserDep,
    service: ReceiptServiceDep,
) -> ReceiptResponse:
    """Create or fully replace the receipt's user-entered details."""
    return await service.upsert_details(user.id, transaction_id, body)


@router.delete("/{transaction_id}/receipt", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    transaction_id: uuid.UUID,
    user: CurrentUserDep,
    service: ReceiptServiceDep,
) -> None:
    """Remove the receipt: details, image metadata, and stored objects."""
    await service.delete_receipt(user.id, transaction_id)


@router.post(
    "/{transaction_id}/receipt/images",
    response_model=ReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipt_image(
    transaction_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUserDep,
    service: ReceiptServiceDep,
) -> ReceiptResponse:
    """Attach one image (JPEG/PNG/WebP, multipart field name `file`).
    Creates the receipt on first upload; at most 10 images per transaction."""
    data = await file.read()
    return await service.add_image(
        user.id,
        transaction_id,
        file_name=file.filename or "",
        content_type=file.content_type or "",
        data=data,
    )


@router.get("/{transaction_id}/receipt/images/{image_id}")
async def get_receipt_image(
    transaction_id: uuid.UUID,
    image_id: uuid.UUID,
    user: CurrentUserDep,
    service: ReceiptServiceDep,
) -> Response:
    """The image bytes themselves, served through the API so the auth
    cookie/token gates access (storage is never exposed directly)."""
    data, image = await service.get_image(user.id, transaction_id, image_id)
    return Response(
        content=data,
        media_type=image.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{image.file_name}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete(
    "/{transaction_id}/receipt/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_receipt_image(
    transaction_id: uuid.UUID,
    image_id: uuid.UUID,
    user: CurrentUserDep,
    service: ReceiptServiceDep,
) -> None:
    await service.delete_image(user.id, transaction_id, image_id)


# --- labels ---


@router.post("/{transaction_id}/labels/{label_id}", response_model=TransactionResponse)
async def assign_label(
    transaction_id: uuid.UUID,
    label_id: uuid.UUID,
    user: CurrentUserDep,
    service: LabelServiceDep,
) -> TransactionResponse:
    """Attach one of the caller's own labels; already-assigned is a no-op,
    not an error."""
    return await service.assign_label(user.id, transaction_id, label_id)


@router.delete("/{transaction_id}/labels/{label_id}", response_model=TransactionResponse)
async def unassign_label(
    transaction_id: uuid.UUID,
    label_id: uuid.UUID,
    user: CurrentUserDep,
    service: LabelServiceDep,
) -> TransactionResponse:
    return await service.unassign_label(user.id, transaction_id, label_id)
