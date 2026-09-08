from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import can_read, can_write_owned, check_edit_token, optional_user, require_user
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.exporters import build_export_csv, build_export_json, reconstruct_answers_from_export
from fipm.ids import hash_token, new_token, short_id
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.schemas import FipCreateRequest, FipImportDoc, FipPatchRequest, fip_out_dict

router = APIRouter(prefix="/fips", tags=["fips"])


def _out(fip: Fip, edit_token: str | None = None) -> dict[str, Any]:
    return fip_out_dict(fip, edit_token)


def _insert_fip(db: Session, settings: Settings, **kwargs: Any) -> Fip:
    for _ in range(5):
        fip = Fip(id=short_id(settings.id_prefix), **kwargs)
        db.add(fip)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(fip)
        return fip
    raise HTTPException(status_code=500, detail="id_generation_failed")


def _authorize_fip_write(fip: Fip, user: User | None, request: Request, db: Session) -> None:
    if fip.owner_id is not None:
        if can_write_owned(fip.owner_id, user):
            return
        if not can_read(fip.owner_id, fip.visibility, user):
            raise HTTPException(status_code=404, detail="not_found")
        raise HTTPException(status_code=403, detail="forbidden")

    # Ownerless (anonymous session) FIP: the session owner may write without a token.
    if fip.session_id is not None and user is not None:
        session_row = db.get(WorkshopSession, fip.session_id)
        if session_row is not None and session_row.owner_id == user.id:
            return
    check_edit_token(request, fip)


def _get_readable_fip(fip_id: str, request: Request, db: Session, user: User | None) -> Fip:
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    if can_read(fip.owner_id, fip.visibility, user):
        return fip
    token = request.headers.get("X-Edit-Token")
    if token and fip.edit_token_hash and hash_token(token) == fip.edit_token_hash:
        return fip
    raise HTTPException(status_code=404, detail="not_found")


@router.post("", status_code=201)
def create_fip(
    body: FipCreateRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    settings = get_settings()
    km = db.get(KnowledgeModel, (body.questionnaire_ref.id, body.questionnaire_ref.version))
    if km is None:
        raise HTTPException(status_code=404, detail="questionnaire_not_found")

    answers = [a.model_dump(mode="json", by_alias=True) for a in body.answers]
    community = body.community.model_dump(mode="json", by_alias=True) if body.community else None
    related_dmps = [d.model_dump(mode="json", by_alias=True) for d in body.related_dmps]
    language = body.language or settings.default_language
    license_ = body.license or "CC0-1.0"

    common: dict[str, Any] = {
        "questionnaire_id": body.questionnaire_ref.id,
        "questionnaire_version": body.questionnaire_ref.version,
        "title": None,
        "community": community,
        "related_dmps": related_dmps,
        "answers": answers,
        "language": language,
        "license": license_,
    }

    if body.session_id:
        session_row = db.get(WorkshopSession, body.session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        if not body.join_code or session_row.join_code != body.join_code:
            raise HTTPException(status_code=403, detail="invalid_join_code")
        if session_row.status != "open":
            raise HTTPException(status_code=409, detail="session_closed")
        edit_token = new_token()
        fip = _insert_fip(
            db,
            settings,
            owner_id=None,
            session_id=session_row.id,
            edit_token_hash=hash_token(edit_token),
            visibility=body.visibility or "link",
            **common,
        )
        return _out(fip, edit_token=edit_token)

    if user is not None:
        fip = _insert_fip(
            db,
            settings,
            owner_id=user.id,
            session_id=None,
            edit_token_hash=None,
            visibility=body.visibility or "private",
            **common,
        )
        return _out(fip)

    raise HTTPException(status_code=400, detail="session_id_or_login_required")


@router.post("/import", status_code=201)
def import_fip(
    body: FipImportDoc, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    settings = get_settings()
    km = db.get(KnowledgeModel, (body.questionnaire_ref.id, body.questionnaire_ref.version))
    if km is None:
        raise HTTPException(status_code=404, detail="questionnaire_not_found")

    fip_data = body.fip
    language = fip_data.get("language") or settings.default_language
    answers = reconstruct_answers_from_export(body.answers, language)

    fip = _insert_fip(
        db,
        settings,
        owner_id=user.id,
        session_id=None,
        edit_token_hash=None,
        visibility=fip_data.get("visibility") or "private",
        questionnaire_id=body.questionnaire_ref.id,
        questionnaire_version=body.questionnaire_ref.version,
        title=None,
        community=fip_data.get("community"),
        related_dmps=fip_data.get("relatedDMPs") or [],
        answers=answers,
        language=language,
        license=fip_data.get("license") or "CC0-1.0",
    )
    return _out(fip)


@router.get("/{fip_id}")
def get_fip(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    fip = _get_readable_fip(fip_id, request, db, user)
    return _out(fip)


@router.patch("/{fip_id}")
def patch_fip(
    fip_id: str,
    body: FipPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    _authorize_fip_write(fip, user, request, db)

    if body.community is not None:
        fip.community = body.community.model_dump(mode="json", by_alias=True)
    if body.answers is not None:
        fip.answers = [a.model_dump(mode="json", by_alias=True) for a in body.answers]
    if body.related_dmps is not None:
        fip.related_dmps = [d.model_dump(mode="json", by_alias=True) for d in body.related_dmps]
    if body.language is not None:
        fip.language = body.language
    if body.license is not None:
        fip.license = body.license
    if body.visibility is not None:
        fip.visibility = body.visibility

    db.commit()
    db.refresh(fip)
    return _out(fip)


@router.delete("/{fip_id}", status_code=204)
def delete_fip(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> None:
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    _authorize_fip_write(fip, user, request, db)
    db.delete(fip)
    db.commit()


@router.post("/{fip_id}/claim")
def claim_fip(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    if fip.owner_id is not None:
        raise HTTPException(status_code=409, detail="already_owned")
    check_edit_token(request, fip)
    fip.owner_id = user.id
    fip.edit_token_hash = None
    db.commit()
    db.refresh(fip)
    return _out(fip)


@router.get("/{fip_id}/export.json")
def export_fip_json(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    fip = _get_readable_fip(fip_id, request, db, user)
    settings = get_settings()
    doc = build_export_json(db, fip, settings)
    return Response(
        content=json.dumps(doc, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fip.id}.json"'},
    )


@router.get("/{fip_id}/export.csv")
def export_fip_csv(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    fip = _get_readable_fip(fip_id, request, db, user)
    settings = get_settings()
    csv_text = build_export_csv(db, fip, settings)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fip.id}.csv"'},
    )


@router.get("/{fip_id}/export.ttl", status_code=501)
def export_fip_ttl(fip_id: str) -> None:
    # Week 3 (rdflib). Not implemented yet.
    raise HTTPException(status_code=501, detail="not_implemented")
