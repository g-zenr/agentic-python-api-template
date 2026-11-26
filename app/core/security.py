"""Password hashing (argon2), JWT access tokens (with token_version), and opaque tokens."""

import hashlib
import secrets
from datetime import timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.messages import Msg
from app.shared.utils.time import utcnow

_hasher = PasswordHash.recommended()


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _hasher.verify(raw, hashed)


def create_access_token(subject: str, token_version: int) -> str:
    now = utcnow()
    exp = now + timedelta(minutes=settings.access_token_ttl_minutes)
    secret = settings.jwt_secret.get_secret_value()
    return jwt.encode(
        {"sub": subject, "tv": token_version, "typ": "access", "iat": now, "exp": exp},
        secret,
        settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> tuple[str, int]:
    """Return (subject, token_version) or raise UnauthorizedError. Rejects non-access tokens."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), [settings.jwt_algorithm]
        )
        if payload.get("typ") != "access":
            raise UnauthorizedError(Msg.AUTH_TOKEN_INVALID)
        return payload["sub"], int(payload.get("tv", 0))
    except (jwt.PyJWTError, KeyError, TypeError) as exc:
        raise UnauthorizedError(Msg.AUTH_TOKEN_INVALID) from exc


def new_opaque_token() -> tuple[str, str]:
    """Return (raw, sha256_hex). Only the hash is ever stored."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
