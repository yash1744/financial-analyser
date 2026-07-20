import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, UserCategoryServiceDep
from app.schemas.user_category import (
    CategoryMappingRequest,
    CategoryMappingResponse,
    UserCategoryCreate,
    UserCategoryResponse,
    UserCategoryUpdate,
)

router = APIRouter(prefix="/user-categories", tags=["user-categories"])


@router.get("", response_model=list[UserCategoryResponse])
async def list_user_categories(
    user: CurrentUserDep, service: UserCategoryServiceDep
) -> list[UserCategoryResponse]:
    """The caller's own rollup categories — private per user, like labels."""
    return await service.list_categories(user.id)


@router.post("", response_model=UserCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_user_category(
    body: UserCategoryCreate, user: CurrentUserDep, service: UserCategoryServiceDep
) -> UserCategoryResponse:
    return await service.create_category(user.id, body)


@router.patch("/{category_id}", response_model=UserCategoryResponse)
async def rename_user_category(
    category_id: uuid.UUID,
    body: UserCategoryUpdate,
    user: CurrentUserDep,
    service: UserCategoryServiceDep,
) -> UserCategoryResponse:
    return await service.rename_category(user.id, category_id, body)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_category(
    category_id: uuid.UUID, user: CurrentUserDep, service: UserCategoryServiceDep
) -> None:
    """Deletes the category and every mapping that rolled a Plaid category
    up into it (category_mappings cascades on the FK)."""
    await service.delete_category(user.id, category_id)


# --- mapping Plaid categories onto a user category ---


@router.get("/mappings", response_model=list[CategoryMappingResponse])
async def list_mappings(
    user: CurrentUserDep, service: UserCategoryServiceDep
) -> list[CategoryMappingResponse]:
    """Every Plaid category → user category assignment the caller has made."""
    return await service.list_mappings(user.id)


@router.put("/mappings/{category_id}", response_model=CategoryMappingResponse)
async def set_mapping(
    category_id: uuid.UUID,
    body: CategoryMappingRequest,
    user: CurrentUserDep,
    service: UserCategoryServiceDep,
) -> CategoryMappingResponse:
    """Roll this Plaid category up into one of the caller's own categories.
    Repoints the mapping if this Plaid category was already mapped
    elsewhere — a Plaid category maps to at most one user category."""
    return await service.set_mapping(user.id, category_id, body.user_category_id)


@router.delete("/mappings/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mapping(
    category_id: uuid.UUID, user: CurrentUserDep, service: UserCategoryServiceDep
) -> None:
    """Unmap this Plaid category — it reverts to showing under its own
    raw name in analytics."""
    await service.remove_mapping(user.id, category_id)
