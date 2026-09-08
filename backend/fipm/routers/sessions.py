from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import can_read, get_readable_published_km, require_user
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.exporters import build_session_export_csv, build_session_export_json
from fipm.ids import join_code as gen_join_code
from fipm.ids import short_id
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.rdf import session_graph, to_turtle
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
    """Owner-only session routes (spec 01-foundations.md §"owner or admin"):
    the session's owner, or an admin, may access it."""
    row = db.get(WorkshopSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    if row.owner_id != user.id and user.role != "admin":
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
    km = db.get(KnowledgeModel, (row.questionnaire_id, row.questionnaire_version))
    # Review finding 4: the join-by-code lookup is public and unauthenticated,
    # so only surface the KM's title when it would itself be readable by an
    # anonymous caller (published and public/link) — never leak a private
    # KM's title through the session's public join code.
    questionnaire_title: dict[str, str] = {}
    if km is not None and km.status == "published" and can_read(km.owner_id, km.visibility, None):
        questionnaire_title = km.title or {}
    return SessionPublicOut(
        id=row.id,
        title=row.title,
        status=row.status,
        questionnaire_ref={"id": row.questionnaire_id, "version": row.questionnaire_version},
        default_language=row.default_language,
        facilitator_name=owner.display_name if owner else "",
        questionnaire_title=questionnaire_title,
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


@router.get("/{session_id}/export.json")
def export_session_json(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Response:
    row = _get_owned_session(session_id, db, user)
    settings = get_settings()
    fips = db.query(Fip).filter(Fip.session_id == row.id).order_by(Fip.created_at).all()
    owner = db.get(User, row.owner_id)
    doc = build_session_export_json(db, row, fips, settings, owner.display_name if owner else "")
    return Response(
        content=json.dumps(doc, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{row.id}.json"'},
    )


@router.get("/{session_id}/export.csv")
def export_session_csv(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Response:
    row = _get_owned_session(session_id, db, user)
    settings = get_settings()
    fips = db.query(Fip).filter(Fip.session_id == row.id).order_by(Fip.created_at).all()
    csv_text = build_session_export_csv(db, row, fips, settings)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{row.id}.csv"'},
    )


@router.get("/{session_id}/export.ttl")
def export_session_ttl(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Response:
    row = _get_owned_session(session_id, db, user)
    settings = get_settings()
    fips = db.query(Fip).filter(Fip.session_id == row.id).order_by(Fip.created_at).all()
    g = session_graph(db, row, fips, settings)
    return Response(
        content=to_turtle(g),
        media_type="text/turtle; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{row.id}.ttl"'},
    )
