from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "vorha_session"


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(str(user_id)),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    user = User(username=payload.username, email=str(payload.email).lower(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "ACCOUNT_EXISTS", "message": "That email or username is already in use."}) from None
    _set_session(response, user.id)
    return AuthResponse(user=UserRead.model_validate(user), message="Account created")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."})
    _set_session(response, user.id)
    return AuthResponse(user=UserRead.model_validate(user), message="Signed in")


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=settings.environment == "production", samesite="lax")
    return {"success": True}
