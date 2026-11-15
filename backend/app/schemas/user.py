from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.roles import Role


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=100)


class AdminUserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    full_name: str | None
    role: Role
    is_active: bool
    created_at: datetime
