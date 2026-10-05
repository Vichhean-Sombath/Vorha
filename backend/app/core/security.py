from datetime import datetime, timedelta, timezone

import hashlib
import hmac

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(subject: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": subject, "exp": expires}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def stream_signature(sound_id: int, external_id: str | None) -> str:
    """Unguessable playback token so /stream cannot be enumerated by anonymous clients."""
    payload = f"vorha-stream:{sound_id}:{external_id or ''}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), payload, hashlib.sha256).hexdigest()[:32]


def stream_signature_matches(token: str | None, sound_id: int, external_id: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(token, stream_signature(sound_id, external_id))
