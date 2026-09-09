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
from fipm.db import SessionLocal
from fipm.ids import hash_token, new_token
from fipm.models import AuthSession, EmailToken, User

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
# spec 05-v1-completion.md §4: POST /api/feedback. Review finding 6: raised
# from 5 to 20 per hour per client IP -- a workshop room full of
# participants sharing one NAT'd IP would otherwise exhaust the original
# cap almost immediately.
FEEDBACK_LIMIT_PER_IP = 20
FEEDBACK_WINDOW_SECONDS = 60 * 60


def client_ip(request: Request) -> str:
    """Review finding 6: `X-Forwarded-For` is attacker-controlled unless a
    trusted reverse proxy sets (and never merely forwards) it, so it's used
    only when the deployment opts in via `FIPM_TRUST_PROXY=true` -- the
    leftmost address in the header is the original client, per the usual
    proxy-chain convention. Falls back to the ASGI-reported peer address
    otherwise, same as before."""
    settings = get_settings()
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
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


def check_feedback_rate_limit(request: Request) -> None:
    """20 per hour per client IP (spec 05-v1-completion.md §4, review
    finding 6). Only *checks* the cap -- call `record_feedback_attempt`
    after the feedback row is actually committed, so a request rejected for
    an unrelated reason (e.g. 403 feedback_disabled) never eats into the
    cap."""
    ip = client_ip(request)
    limited, retry = _rate_limiter.is_limited(
        f"feedback-ip:{ip}", FEEDBACK_LIMIT_PER_IP, FEEDBACK_WINDOW_SECONDS
    )
    if limited:
        _raise_rate_limited(retry)


def record_feedback_attempt(ip: str) -> None:
    """Review finding 6: called only after a successful POST /api/feedback
    insert, not before the work is attempted -- pairs with
    `check_feedback_rate_limit`."""
    _rate_limiter.record(f"feedback-ip:{ip}", FEEDBACK_WINDOW_SECONDS)


# spec 07-mail-and-migration.md §2/§3: verification resend and password-reset
# rate limits.
RESEND_LIMIT_PER_USER = 3
RESEND_LIMIT_PER_IP = 10
RESEND_WINDOW_SECONDS = 60 * 60
PASSWORD_RESET_LIMIT_PER_EMAIL = 3
PASSWORD_RESET_LIMIT_PER_IP = 10
PASSWORD_RESET_WINDOW_SECONDS = 60 * 60


def check_resend_rate_limit(request: Request, user_id: str) -> None:
    """spec §2: 3/hour per user id, 10/hour per client ip -> 429 Retry-After."""
    ip = client_ip(request)
    limited_user, retry1 = _rate_limiter.is_limited(
        f"resend-user:{user_id}", RESEND_LIMIT_PER_USER, RESEND_WINDOW_SECONDS
    )
    limited_ip, retry2 = _rate_limiter.is_limited(
        f"resend-ip:{ip}", RESEND_LIMIT_PER_IP, RESEND_WINDOW_SECONDS
    )
    if limited_user or limited_ip:
        _raise_rate_limited(max(retry1, retry2))


def record_resend_attempt(request: Request, user_id: str) -> None:
    ip = client_ip(request)
    _rate_limiter.record(f"resend-user:{user_id}", RESEND_WINDOW_SECONDS)
    _rate_limiter.record(f"resend-ip:{ip}", RESEND_WINDOW_SECONDS)


def password_reset_over_limit(request: Request, email_lower: str) -> bool:
    """spec §3: 3/hour per lowercased email, 10/hour per ip -- over-limit
    still returns 202 (a 429 keyed on an email is itself an enumeration
    oracle), so this returns a bool for the caller to silently drop the mail
    on, rather than raising."""
    ip = client_ip(request)
    limited_email, _ = _rate_limiter.is_limited(
        f"pwreset-email:{email_lower}",
        PASSWORD_RESET_LIMIT_PER_EMAIL,
        PASSWORD_RESET_WINDOW_SECONDS,
    )
    limited_ip, _ = _rate_limiter.is_limited(
        f"pwreset-ip:{ip}", PASSWORD_RESET_LIMIT_PER_IP, PASSWORD_RESET_WINDOW_SECONDS
    )
    return limited_email or limited_ip


def record_password_reset_attempt(request: Request, email_lower: str) -> None:
    ip = client_ip(request)
    _rate_limiter.record(f"pwreset-email:{email_lower}", PASSWORD_RESET_WINDOW_SECONDS)
    _rate_limiter.record(f"pwreset-ip:{ip}", PASSWORD_RESET_WINDOW_SECONDS)


# ---------------------------------------------------------------------------
# Email tokens (spec 07-mail-and-migration.md §0/§2/§3): verify_email and
# password_reset, sharing one table. Only the sha256 hex of the plaintext
# token is ever stored; the plaintext lives in the mail and nowhere else.
# ---------------------------------------------------------------------------


def issue_email_token(db: Session, user: User, purpose: str, email: str, ttl_hours: int) -> str:
    """Delete the user's earlier unused tokens of this purpose (spec §2:
    "issuing a new token of a purpose deletes that user's earlier unused
    ones of the same purpose"), then create and return the new plaintext
    token (only its hash is persisted)."""
    now = datetime.now(UTC)
    db.execute(
        delete(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
    )
    token = new_token()
    db.add(
        EmailToken(
            id=hash_token(token),
            user_id=user.id,
            purpose=purpose,
            email=email,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            used_at=None,
        )
    )
    db.commit()
    return token


def resolve_email_token(db: Session, token: str, purpose: str) -> tuple[EmailToken, User]:
    """400 `invalid_token` (unknown id, wrong purpose, already used, or the
    stored `email` no longer matches the user's current address -- spec §2)
    raised as HTTPException; 410 `token_expired` when only expiry fails, so
    the UI can distinguish "dead" from "offer a new link". Returns the row
    and its user on success; the caller marks it used."""
    row = db.get(EmailToken, hash_token(token))
    if row is None or row.purpose != purpose or row.used_at is not None:
        raise HTTPException(status_code=400, detail="invalid_token")
    user = db.get(User, row.user_id)
    if user is None or user.email != row.email:
        raise HTTPException(status_code=400, detail="invalid_token")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="token_expired")
    return row, user


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


# ---------------------------------------------------------------------------
# must_change_password enforcement (spec 05-v1-completion.md §1)
# ---------------------------------------------------------------------------

_PASSWORD_CHANGE_EXEMPT_PATHS = {
    "/api/auth/password",
    "/api/auth/logout",
    # Review finding 3: a signed-in user flagged must_change_password can
    # still hold a stale cookie for a *different* account (or simply be
    # re-submitting the login form) -- login and register must stay
    # reachable rather than surfacing an unrelated 403
    # password_change_required on them.
    "/api/auth/login",
    "/api/auth/register",
}


async def password_change_middleware(request: Request, call_next):
    """A signed-in user with `must_change_password` gets 403
    `password_change_required` on any non-GET `/api/*` request except
    changing the password or logging out; GET stays open so the SPA still
    renders (`GET /api/auth/me` included).

    Implemented as middleware rather than inside `require_user`: several
    write routes that must also be covered -- notably `PATCH`/`DELETE
    /api/fips/{id}` -- authorize through `optional_user` (anonymous
    edit-token writers are allowed there too), so a check living only in
    `require_user` would miss them."""
    if request.method != "GET" and request.url.path.startswith("/api/"):
        if request.url.path not in _PASSWORD_CHANGE_EXEMPT_PATHS:
            settings = get_settings()
            db = SessionLocal()
            try:
                user = get_session_user(request, db, settings)
            finally:
                db.close()
            if user is not None and user.must_change_password:
                return JSONResponse(status_code=403, content={"detail": "password_change_required"})
    return await call_next(request)
