from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class UserRegister(BaseModel):
    email: EmailStr = Field(..., description="User login email address")
    password: str = Field(..., min_length=6, description="Cleartext password")
    role: Optional[UserRole] = Field(UserRole.user, description="Assigned authorization role")


class UserLogin(BaseModel):
    email: EmailStr = Field(...)
    password: str = Field(...)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True
