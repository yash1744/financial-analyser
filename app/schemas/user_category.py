import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class UserCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class UserCategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryMappingRequest(BaseModel):
    user_category_id: uuid.UUID


class CategoryMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: uuid.UUID
    user_category_id: uuid.UUID
