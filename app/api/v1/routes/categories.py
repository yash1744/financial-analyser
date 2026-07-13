from fastapi import APIRouter

from app.api.deps import CategoryQueryServiceDep
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(service: CategoryQueryServiceDep) -> list[CategoryResponse]:
    return await service.list_categories()
