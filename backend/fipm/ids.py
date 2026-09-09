"""Identifier schemes: short ids, join codes, opaque tokens."""

from __future__ import annotations

import hashlib
import secrets

# Crockford base32, no I/L/O/U.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _crockford(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def short_id(prefix: str = "") -> str:
    """8 Crockford base32 chars drawn from 40 random bits, with an optional prefix."""
    code = _crockford(secrets.randbits(40), 8)
    return f"{prefix}{code}"


def join_code() -> str:
    """6 Crockford base32 chars (uppercase, human-dictatable), drawn from 30 random bits."""
    return _crockford(secrets.randbits(30), 6)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_user_id() -> str:
    """26-char hex user id."""
    return secrets.token_hex(13)


def new_feedback_id() -> str:
    """26-char hex feedback id (spec 05-v1-completion.md §4)."""
    return secrets.token_hex(13)


def temp_password() -> str:
    """12 Crockford base32 chars via secrets.choice (spec 05-v1-completion.md
    §1): no I/L/O/U, so it can be dictated over the phone. An admin-issued
    temporary password shown once in the response body."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(12))
