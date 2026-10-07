import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TelegramLoginRequest, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "vorha_session"
TELEGRAM_NONCE_COOKIE = "vorha_telegram_nonce"
TELEGRAM_ISSUER = "https://oauth.telegram.org"
TELEGRAM_JWKS_URL = f"{TELEGRAM_ISSUER}/.well-known/jwks.json"
TELEGRAM_KEYS = jwt.PyJWKClient(TELEGRAM_JWKS_URL, cache_jwk_set=True, lifespan=3600)


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
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
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


@router.get("/telegram/nonce")
def telegram_login_nonce(response: Response) -> dict[str, str]:
    if (
        not settings.telegram_client_id
        or not settings.telegram_bot_id
        or not settings.telegram_bot_id.isdigit()
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "TELEGRAM_LOGIN_NOT_CONFIGURED",
                "message": "Telegram login needs TELEGRAM_CLIENT_ID and a numeric TELEGRAM_BOT_ID. Set TELEGRAM_BOT_ID to the ID of the bot configured for Telegram Login.",
            },
        )
    nonce = secrets.token_urlsafe(32)
    response.set_cookie(
        TELEGRAM_NONCE_COOKIE,
        nonce,
        max_age=600,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/api/v1/auth/telegram",
    )
    return {"client_id": settings.telegram_client_id, "bot_id": settings.telegram_bot_id, "nonce": nonce}


@router.post("/telegram/login", response_model=AuthResponse)
def telegram_login(
    payload: TelegramLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    nonce = request.cookies.get(TELEGRAM_NONCE_COOKIE)
    if not nonce or not settings.telegram_client_id:
        raise HTTPException(status_code=401, detail={"code": "TELEGRAM_LOGIN_EXPIRED", "message": "Restart Telegram sign-in and try again."})
    try:
        signing_key = TELEGRAM_KEYS.get_signing_key_from_jwt(payload.id_token)
        claims = jwt.decode(
            payload.id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.telegram_client_id,
            issuer=TELEGRAM_ISSUER,
            leeway=30,
            options={"require": ["exp", "iat", "sub", "nonce"]},
        )
        if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(claims["nonce"], nonce):
            raise jwt.InvalidTokenError("Invalid nonce")
        telegram_id = str(claims["sub"])
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            username_seed = claims.get("preferred_username") or f"telegram_{telegram_id}"
            username_base = "".join(char for char in str(username_seed).lower() if char.isalnum() or char in "_.-")[:42].strip("_.-") or f"telegram_{telegram_id}"
            username = username_base
            suffix = 1
            while db.scalar(select(User.id).where(User.username == username)) is not None:
                suffix += 1
                username = f"{username_base[:45]}_{suffix}"
            user = User(username=username, telegram_id=telegram_id)
            db.add(user)
            try:
                db.commit()
                db.refresh(user)
            except IntegrityError:
                db.rollback()
                user = db.scalar(select(User).where(User.telegram_id == telegram_id))
                if user is None:
                    raise
        response.delete_cookie(TELEGRAM_NONCE_COOKIE, path="/api/v1/auth/telegram", httponly=True, secure=settings.environment == "production", samesite="lax")
        _set_session(response, user.id)
        return AuthResponse(user=UserRead.model_validate(user), message="Signed in with Telegram")
    except jwt.PyJWTError:
        db.rollback()
        response.delete_cookie(TELEGRAM_NONCE_COOKIE, path="/api/v1/auth/telegram", httponly=True, secure=settings.environment == "production", samesite="lax")
        raise HTTPException(status_code=401, detail={"code": "INVALID_TELEGRAM_TOKEN", "message": "Telegram sign-in could not be verified. Please try again."}) from None
