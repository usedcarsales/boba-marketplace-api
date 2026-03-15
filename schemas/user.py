from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    username: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    display_name: str | None
    avatar_url: str | None
    bio: str | None
    role: str
    rating: float
    total_sales: int
    total_purchases: int
    stripe_onboarding_complete: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPublicResponse(BaseModel):
    id: UUID
    username: str
    display_name: str | None
    avatar_url: str | None
    bio: str | None
    rating: float
    total_sales: int
    created_at: datetime

    model_config = {"from_attributes": True}
