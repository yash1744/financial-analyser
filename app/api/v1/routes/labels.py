import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, LabelServiceDep
from app.schemas.label import LabelCreate, LabelResponse, LabelUpdate

router = APIRouter(prefix="/labels", tags=["labels"])


@router.get("", response_model=list[LabelResponse])
async def list_labels(
    user: CurrentUserDep, service: LabelServiceDep
) -> list[LabelResponse]:
    """The caller's own labels — private per user, unlike categories."""
    return await service.list_labels(user.id)


@router.post("", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
async def create_label(
    body: LabelCreate, user: CurrentUserDep, service: LabelServiceDep
) -> LabelResponse:
    return await service.create_label(user.id, body)


@router.patch("/{label_id}", response_model=LabelResponse)
async def rename_label(
    label_id: uuid.UUID,
    body: LabelUpdate,
    user: CurrentUserDep,
    service: LabelServiceDep,
) -> LabelResponse:
    return await service.rename_label(user.id, label_id, body)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    label_id: uuid.UUID, user: CurrentUserDep, service: LabelServiceDep
) -> None:
    """Deletes the label and removes it from every transaction it was
    assigned to (transaction_labels cascades on the FK)."""
    await service.delete_label(user.id, label_id)
