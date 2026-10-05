from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(request: Request, db: Session = Depends(get_db), credentials=Depends(bearer)) -> User:
    token = request.cookies.get("vorha_session")
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    import jwt
    from jwt import InvalidTokenError

    from app.core.config import settings

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub", ""))
    except (InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Sign in again.", headers={"WWW-Authenticate": "Bearer"}) from None
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is no longer valid.")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db), credentials=Depends(bearer)) -> User | None:
    """Resolve the session if one is present, without rejecting anonymous callers."""
    token = request.cookies.get("vorha_session")
    if not token and credentials:
        token = credentials.credentials
    if not token:
        return None
    import jwt
    from jwt import InvalidTokenError

    from app.core.config import settings

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub", ""))
    except (InvalidTokenError, ValueError, TypeError):
        return None
    return db.scalar(select(User).where(User.id == user_id))
