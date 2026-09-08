from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import get_readable_published_km, require_user
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.ids import join_code as gen_join_code
from fipm.ids import short_id
from fipm.models import Fip, User, WorkshopSession
from fipm.schemas import (
    SessionCreateRequest,
    SessionPatchRequest,
    SessionPublicOut,
    fip_out_dict,
    session_to_out,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _insert_session(db: Session, settings: Settings, **kwargs: Any) -> WorkshopSession:
    for _ in range(5):
        row = WorkshopSession(id=short_id(settings.id_prefix), join_code=gen_join_code(), **kwargs)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(row)
        return row
    raise HTTPException(status_code=500, detail="id_generation_failed")


def _get_owned_session(session_id: str, db: Session, user: User) -> WorkshopSession:
    row = db.get(WorkshopSession, session_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(status_code=404, detail="not_found")
    return row


@router.post("", status_code=201)
def create_session(
    body: SessionCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    settings = get_settings()
    get_readable_published_km(db, body.questionnaire_ref.id, body.questionnaire_ref.version, user)
    row = _insert_session(
        db,
        settings,
        owner_id=user.id,
        questionnaire_id=body.questionnaire_ref.id,
        questionnaire_version=body.questionnaire_ref.version,
        default_language=body.default_language,
        title=body.title,
        status="open",
    )
    return session_to_out(row, settings.base_url).model_dump(mode="json", by_alias=True)


@router.get("/by-code/{join_code}", response_model=SessionPublicOut)
def get_session_by_code(join_code: str, db: Session = Depends(get_db)) -> SessionPublicOut:
    row = db.query(WorkshopSession).filter(WorkshopSession.join_code == join_code).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    owner = db.get(User, row.owner_id)
    return SessionPublicOut(
        id=row.id,
        title=row.title,
        status=row.status,
        questionnaire_ref={"id": row.questionnaire_id, "version": row.questionnaire_version},
        default_language=row.default_language,
        facilitator_name=owner.display_name if owner else "",
    )


@router.get("/{session_id}")
def get_session(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    row = _get_owned_session(session_id, db, user)
    settings = get_settings()
    return session_to_out(row, settings.base_url).model_dump(mode="json", by_alias=True)


@router.patch("/{session_id}")
def patch_session(
    session_id: str,
    body: SessionPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    row = _get_owned_session(session_id, db, user)
    if body.title is not None:
        row.title = body.title
    if body.status is not None:
        row.status = body.status
    if body.default_language is not None:
        row.default_language = body.default_language
    db.commit()
    db.refresh(row)
    settings = get_settings()
    return session_to_out(row, settings.base_url).model_dump(mode="json", by_alias=True)


@router.get("/{session_id}/fips")
def list_session_fips(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    row = _get_owned_session(session_id, db, user)
    rows = db.query(Fip).filter(Fip.session_id == row.id).order_by(Fip.created_at).all()
    items = [fip_out_dict(f) for f in rows]
    return {"items": items, "total": len(items)}
