from __future__ import annotations

import json
import secrets
from typing import Any, get_args

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import (
    can_read,
    can_write_owned,
    check_edit_token,
    get_readable_published_km,
    optional_user,
    require_user,
)
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.exporters import build_export_csv, build_export_json, reconstruct_answers_from_export
from fipm.ids import hash_token, new_token, short_id
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.rdf import fip_graph, to_jsonld, to_turtle
from fipm.schemas import (
    Answer,
    FipCreateRequest,
    FipImportDoc,
    FipPatchRequest,
    Language,
    Visibility,
    fip_out_dict,
)

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


def _session_owner_has_access(fip: Fip, user: User | None, db: Session) -> bool:
    """The owner of the session a (session-scoped) FIP belongs to may access it
    without an edit token, for both reads and writes."""
    if fip.session_id is None or user is None:
        return False
    session_row = db.get(WorkshopSession, fip.session_id)
    return session_row is not None and session_row.owner_id == user.id


def _authorize_fip_write(fip: Fip, user: User | None, request: Request, db: Session) -> None:
    if fip.owner_id is not None:
        # Owned FIPs: owner/admin, or (review finding 2) the owner of the
        # session the FIP was claimed out of, matching spec 02-core-flows.md
        # A4's "facilitator ... keep write access" to FIPs in their session.
        is_admin = user is not None and user.role == "admin"
        is_session_owner = fip.session_id is not None and _session_owner_has_access(fip, user, db)
        if can_write_owned(fip.owner_id, user) or is_session_owner:
            # A claimed FIP that still carries its originating session_id
            # stays frozen for its new owner once that session closes,
            # unless the caller is the session owner or an admin.
            if fip.session_id is not None and not (is_admin or is_session_owner):
                session_row = db.get(WorkshopSession, fip.session_id)
                if session_row is not None and session_row.status == "closed":
                    raise HTTPException(status_code=409, detail="session_closed")
            return
        if not can_read(fip.owner_id, fip.visibility, user):
            raise HTTPException(status_code=404, detail="not_found")
        raise HTTPException(status_code=403, detail="forbidden")

    # Ownerless (anonymous session) FIP: the session owner or an admin may
    # write without a token, even once the session is closed.
    if _session_owner_has_access(fip, user, db):
        return
    if user is not None and user.role == "admin":
        return

    # Check the edit token before the session's status (review finding 7):
    # a caller without a valid token gets 403 edit_token_required rather
    # than learning the session is closed.
    check_edit_token(request, fip)

    # spec 02-core-flows.md §5.4: a closed session makes its anonymous FIPs
    # read-only for everyone else, regardless of edit-token validity.
    if fip.session_id is not None:
        session_row = db.get(WorkshopSession, fip.session_id)
        if session_row is not None and session_row.status == "closed":
            raise HTTPException(status_code=409, detail="session_closed")


def _get_readable_fip(fip_id: str, request: Request, db: Session, user: User | None) -> Fip:
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    if can_read(fip.owner_id, fip.visibility, user):
        return fip
    if _session_owner_has_access(fip, user, db):
        return fip
    token = request.headers.get("X-Edit-Token")
    if (
        token
        and fip.edit_token_hash
        and secrets.compare_digest(hash_token(token), fip.edit_token_hash)
    ):
        return fip
    raise HTTPException(status_code=404, detail="not_found")


def _known_question_ids(km: KnowledgeModel) -> set[str]:
    content = km.content or {}
    return {
        question["id"]
        for section in content.get("sections", [])
        for question in section.get("questions", [])
    }


def _validate_question_ids(answers: list[Answer], km: KnowledgeModel) -> None:
    valid_ids = _known_question_ids(km)
    if any(a.question_id not in valid_ids for a in answers):
        raise HTTPException(status_code=400, detail="unknown_question_id")


@router.post("", status_code=201)
def create_fip(
    body: FipCreateRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    settings = get_settings()

    session_row: WorkshopSession | None = None
    if body.session_id:
        session_row = db.get(WorkshopSession, body.session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        if not body.join_code or not secrets.compare_digest(body.join_code, session_row.join_code):
            raise HTTPException(status_code=403, detail="invalid_join_code")
        if session_row.status != "open":
            raise HTTPException(status_code=409, detail="session_closed")
        # The session already pins a questionnaire; a body ref that disagrees
        # with it is a client error rather than something to silently override.
        if (
            body.questionnaire_ref.id != session_row.questionnaire_id
            or body.questionnaire_ref.version != session_row.questionnaire_version
        ):
            raise HTTPException(status_code=400, detail="questionnaire_ref_mismatch")
        questionnaire_id = session_row.questionnaire_id
        questionnaire_version = session_row.questionnaire_version
    else:
        questionnaire_id = body.questionnaire_ref.id
        questionnaire_version = body.questionnaire_ref.version

    km = get_readable_published_km(db, questionnaire_id, questionnaire_version, user)
    _validate_question_ids(body.answers, km)

    answers = [a.model_dump(mode="json", by_alias=True) for a in body.answers]
    community = body.community.model_dump(mode="json", by_alias=True) if body.community else None
    related_dmps = [d.model_dump(mode="json", by_alias=True) for d in body.related_dmps]
    language = body.language or settings.default_language
    license_ = body.license or "CC0-1.0"

    common: dict[str, Any] = {
        "questionnaire_id": questionnaire_id,
        "questionnaire_version": questionnaire_version,
        "title": community.get("name") if community else None,
        "community": community,
        "related_dmps": related_dmps,
        "answers": answers,
        "language": language,
        "license": license_,
    }

    if session_row is not None:
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
    km = get_readable_published_km(
        db, body.questionnaire_ref.id, body.questionnaire_ref.version, user
    )

    fip_data = body.fip
    language = fip_data.get("language") or settings.default_language
    if language not in get_args(Language):
        raise HTTPException(status_code=400, detail="invalid_language")
    visibility = fip_data.get("visibility") or "private"
    if visibility not in get_args(Visibility):
        raise HTTPException(status_code=400, detail="invalid_visibility")

    try:
        reconstructed = reconstruct_answers_from_export(body.answers, language)
        answers = [Answer.model_validate(a) for a in reconstructed]
    except (KeyError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="invalid_answers") from exc

    _validate_question_ids(answers, km)
    community = fip_data.get("community")

    fip = _insert_fip(
        db,
        settings,
        owner_id=user.id,
        session_id=None,
        edit_token_hash=None,
        visibility=visibility,
        questionnaire_id=body.questionnaire_ref.id,
        questionnaire_version=body.questionnaire_ref.version,
        title=community.get("name") if community else None,
        community=community,
        related_dmps=fip_data.get("relatedDMPs") or [],
        answers=[a.model_dump(mode="json", by_alias=True) for a in answers],
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
        community = body.community.model_dump(mode="json", by_alias=True)
        fip.community = community
        fip.title = community.get("name")
    if body.answers is not None:
        km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
        if km is not None:
            _validate_question_ids(body.answers, km)
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
    # Review finding 2: claiming is only for token holders, so no owner/admin
    # exemption here (unlike _authorize_fip_write's ownerless-write path).
    if fip.session_id is not None:
        session_row = db.get(WorkshopSession, fip.session_id)
        if session_row is not None and session_row.status == "closed":
            raise HTTPException(status_code=409, detail="session_closed")
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


@router.get("/{fip_id}/export.ttl")
def export_fip_ttl(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    fip = _get_readable_fip(fip_id, request, db, user)
    settings = get_settings()
    g = fip_graph(db, fip, settings)
    return Response(
        content=to_turtle(g),
        media_type="text/turtle; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fip.id}.ttl"'},
    )


@router.get("/{fip_id}/export.jsonld")
def export_fip_jsonld(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    fip = _get_readable_fip(fip_id, request, db, user)
    settings = get_settings()
    g = fip_graph(db, fip, settings)
    return Response(
        content=to_jsonld(g),
        media_type="application/ld+json",
        headers={"Content-Disposition": f'attachment; filename="{fip.id}.jsonld"'},
    )
