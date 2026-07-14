from fastapi import APIRouter

from app.api.deps import CategoryQueryServiceDep, CurrentUserDep
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    user: CurrentUserDep, service: CategoryQueryServiceDep
) -> list[CategoryResponse]:
    """Global category taxonomy (auth required for consistency; the data
    itself is not user-specific)."""
    return await service.list_categories()
