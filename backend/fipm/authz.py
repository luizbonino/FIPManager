"""Authorization: session/role dependencies, visibility rules, edit tokens."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from fipm.auth import get_session_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.ids import hash_token
from fipm.models import Fip, User


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    user = get_session_user(request, db, settings)
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    settings = get_settings()
    return get_session_user(request, db, settings)


def can_read(owner_id: str | None, visibility: str, user: User | None) -> bool:
    """Owner or admin always; public/link readable by anyone; private only owner/admin."""
    if user is not None and (
        user.role == "admin" or (owner_id is not None and user.id == owner_id)
    ):
        return True
    return visibility in ("public", "link")


def can_write_owned(owner_id: str | None, user: User | None) -> bool:
    """Write on an owned object: owner or admin only."""
    if user is None:
        return False
    return user.role == "admin" or (owner_id is not None and user.id == owner_id)


def check_edit_token(request: Request, fip: Fip) -> None:
    """Raise 403 edit_token_required unless X-Edit-Token matches the FIP's hash."""
    token = request.headers.get("X-Edit-Token")
    if not token or fip.edit_token_hash is None or hash_token(token) != fip.edit_token_hash:
        raise HTTPException(status_code=403, detail="edit_token_required")


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")
