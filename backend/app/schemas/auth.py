from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import ORMModel


class RegisterRequest(ORMModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(ORMModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TelegramLoginRequest(ORMModel):
    id_token: str = Field(min_length=20, max_length=8192)


class UserRead(ORMModel):
    id: int
    username: str
    email: EmailStr | None
    created_at: datetime


class AuthResponse(ORMModel):
    user: UserRead
    message: str = "Signed in"
