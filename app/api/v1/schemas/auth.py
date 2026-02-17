"""Authentication schemas."""

from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str | None
    is_active: bool
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
