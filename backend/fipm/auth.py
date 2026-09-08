"""Password hashing, cookie sessions, CSRF middleware, in-process rate limiter."""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from fipm.config import Settings, get_settings
from fipm.ids import hash_token, new_token
from fipm.models import AuthSession, User

COOKIE_NAME = "fipm_session"
_LAST_SEEN_REFRESH_INTERVAL = timedelta(minutes=5)

ph = PasswordHasher()
_DUMMY_HASH = ph.hash("dummy-password-used-for-timing-safety-only")


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return ph.check_needs_rehash(password_hash)


def dummy_verify() -> None:
    """Run when the user is absent, so login timing doesn't leak existence."""
    try:
        ph.verify(_DUMMY_HASH, "irrelevant-password")
    except VerifyMismatchError:
        pass


# ---------------------------------------------------------------------------
# Rate limiting: in-process dict[key, deque[timestamp]], monotonic clock.
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}

    def _prune(self, key: str, window_seconds: float) -> deque[float]:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        return bucket

    def is_limited(self, key: str, limit: int, window_seconds: float) -> tuple[bool, float]:
        bucket = self._prune(key, window_seconds)
        if len(bucket) >= limit:
            retry_after = window_seconds - (time.monotonic() - bucket[0])
            return True, max(retry_after, 0.0)
        return False, 0.0

    def record(self, key: str, window_seconds: float) -> None:
        bucket = self._prune(key, window_seconds)
        bucket.append(time.monotonic())


_rate_limiter = RateLimiter()


def reset_rate_limits() -> None:
    """Test-only helper: clear all rate-limit buckets between tests."""
    _rate_limiter._buckets.clear()


LOGIN_LIMIT_PER_EMAIL_IP = 10
LOGIN_LIMIT_PER_IP = 30
LOGIN_WINDOW_SECONDS = 15 * 60
REGISTER_LIMIT_PER_IP = 5
REGISTER_WINDOW_SECONDS = 60 * 60


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _raise_rate_limited(retry_after: float) -> None:
    raise HTTPException(
        status_code=429,
        detail="rate_limited",
        headers={"Retry-After": str(int(retry_after) + 1)},
    )


def check_login_rate_limit(request: Request, email: str) -> None:
    """Call before attempting to verify a password; raises 429 if already over."""
    ip = client_ip(request)
    limited_email, retry1 = _rate_limiter.is_limited(
        f"login-email:{email}:{ip}", LOGIN_LIMIT_PER_EMAIL_IP, LOGIN_WINDOW_SECONDS
    )
    limited_ip, retry2 = _rate_limiter.is_limited(
        f"login-ip:{ip}", LOGIN_LIMIT_PER_IP, LOGIN_WINDOW_SECONDS
    )
    if limited_email or limited_ip:
        _raise_rate_limited(max(retry1, retry2))


def record_login_failure(request: Request, email: str) -> None:
    ip = client_ip(request)
    _rate_limiter.record(f"login-email:{email}:{ip}", LOGIN_WINDOW_SECONDS)
    _rate_limiter.record(f"login-ip:{ip}", LOGIN_WINDOW_SECONDS)


def check_register_rate_limit(request: Request) -> None:
    ip = client_ip(request)
    limited, retry = _rate_limiter.is_limited(
        f"register-ip:{ip}", REGISTER_LIMIT_PER_IP, REGISTER_WINDOW_SECONDS
    )
    if limited:
        _raise_rate_limited(retry)
    _rate_limiter.record(f"register-ip:{ip}", REGISTER_WINDOW_SECONDS)


# ---------------------------------------------------------------------------
# Cookie sessions
# ---------------------------------------------------------------------------


def create_auth_session(db: Session, user: User, settings: Settings) -> tuple[AuthSession, str]:
    token = new_token()
    now = datetime.now(UTC)
    session_row = AuthSession(
        id=hash_token(token),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(days=settings.session_ttl_days),
        last_seen_at=now,
    )
    db.add(session_row)
    db.commit()
    return session_row, token


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_ttl_days * 24 * 60 * 60,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/", samesite="lax", secure=settings.cookie_secure)


def get_session_user(request: Request, db: Session, settings: Settings) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    token_hash = hash_token(token)
    session_row = db.get(AuthSession, token_hash)
    if session_row is None:
        return None
    now = datetime.now(UTC)
    expires_at = session_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        db.execute(delete(AuthSession).where(AuthSession.id == token_hash))
        db.commit()
        return None
    last_seen_at = session_row.last_seen_at
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    if now - last_seen_at > _LAST_SEEN_REFRESH_INTERVAL:
        session_row.last_seen_at = now
        db.commit()
    user = db.get(User, session_row.user_id)
    return user


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.id == hash_token(token)))
    db.commit()


def revoke_all_sessions(db: Session, user_id: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.commit()


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def _scheme_host(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _origin_allowed(origin: str, settings: Settings) -> bool:
    candidate = _scheme_host(origin)
    allowed = {_scheme_host(settings.base_url)}
    allowed.update(_scheme_host(o) for o in settings.allowed_origins_list)
    return candidate in allowed


async def csrf_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api"):
        settings = get_settings()
        origin = request.headers.get("origin") or request.headers.get("referer")
        if not origin or not _origin_allowed(origin, settings):
            return JSONResponse(status_code=403, content={"detail": "csrf_failed"})
    return await call_next(request)
