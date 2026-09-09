from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import get_readable_published_km, require_user
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.exporters import (
    build_session_export_csv,
    build_session_export_json,
    resolve_session_questionnaire_refs,
)
from fipm.ids import join_code as gen_join_code
from fipm.ids import short_id
from fipm.km_content import ContentError, validate_langmap
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.rdf import session_graph, to_turtle
from fipm.schemas import (
    QuestionnaireRef,
    QuestionnaireRefLabelled,
    SessionCreateRequest,
    SessionPatchRequest,
    SessionPublicOut,
    area_label_for_refs,
    fip_out_dict,
    known_question_ids_for_km,
    session_to_out,
    total_questions_for_km,
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


def _prepare_questionnaire_refs(
    db: Session,
    user: User,
    questionnaire_ref: QuestionnaireRef | None,
    questionnaire_refs: list[QuestionnaireRefLabelled] | None,
) -> tuple[list[dict[str, Any]] | None, str, str, list[ContentError]]:
    """spec 08-workshop-picklists.md §3.1: validate and resolve a session's
    ref(s), shared by `create_session` and `patch_session`. Returns
    `(refs_to_store, primary_id, primary_version, label_errors)`:
    `refs_to_store` is None when the caller only sent the legacy single
    `questionnaireRef` (the `questionnaire_refs` column stays NULL, derived
    at read time -- spec §0); `primary_id`/`primary_version` always name
    refs[0], for the `questionnaire_id`/`questionnaire_version` FK columns.
    Raises 400 `questionnaire_ref_conflict`/`duplicate_questionnaire_ref`
    and 404 (via `get_readable_published_km`) directly; a non-empty
    `label_errors` is the caller's cue to return the `invalid_content`
    envelope instead of committing."""
    if questionnaire_refs:
        first = questionnaire_refs[0]
        if questionnaire_ref is not None and (
            questionnaire_ref.id != first.id or questionnaire_ref.version != first.version
        ):
            raise HTTPException(status_code=400, detail="questionnaire_ref_conflict")
        seen: set[tuple[str, str]] = set()
        errors: list[ContentError] = []
        for idx, ref in enumerate(questionnaire_refs):
            key = (ref.id, ref.version)
            if key in seen:
                raise HTTPException(status_code=400, detail="duplicate_questionnaire_ref")
            seen.add(key)
            get_readable_published_km(db, ref.id, ref.version, user)
            errors += validate_langmap(
                ref.label, f"questionnaireRefs[{idx}].label", require_en=False, max_len=80
            )
        refs_to_store = [
            {"id": ref.id, "version": ref.version, "label": ref.label} for ref in questionnaire_refs
        ]
        return refs_to_store, first.id, first.version, errors

    if questionnaire_ref is None:
        # SessionCreateRequest's own model validator already 422s this
        # before the router runs; reachable from patch_session only if it
        # ever calls this helper with both args None, which it doesn't.
        raise HTTPException(status_code=422, detail="questionnaire_ref_required")

    get_readable_published_km(db, questionnaire_ref.id, questionnaire_ref.version, user)
    return None, questionnaire_ref.id, questionnaire_ref.version, []


@router.post("", status_code=201)
def create_session(
    body: SessionCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Any:
    settings = get_settings()
    refs_to_store, primary_id, primary_version, errors = _prepare_questionnaire_refs(
        db, user, body.questionnaire_ref, body.questionnaire_refs
    )
    if errors:
        return JSONResponse(
            status_code=400, content={"detail": "invalid_content", "errors": errors}
        )
    row = _insert_session(
        db,
        settings,
        owner_id=user.id,
        questionnaire_id=primary_id,
        questionnaire_version=primary_version,
        questionnaire_refs=refs_to_store,
        default_language=body.default_language,
        title=body.title,
        status="open",
    )
    refs_out = resolve_session_questionnaire_refs(db, row)
    return session_to_out(row, settings.base_url, refs_out).model_dump(mode="json", by_alias=True)


@router.get("/by-code/{join_code}", response_model=SessionPublicOut)
def get_session_by_code(join_code: str, db: Session = Depends(get_db)) -> SessionPublicOut:
    row = db.query(WorkshopSession).filter(WorkshopSession.join_code == join_code).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    owner = db.get(User, row.owner_id)
    # Review finding 4 / spec 08-workshop-picklists.md §5.8: the join-by-code
    # lookup is public and unauthenticated, so only surface a ref's title
    # when it would itself be readable by an anonymous caller (published and
    # public/link) -- never leak a private KM's title through the session's
    # public join code. `resolve_session_questionnaire_refs` applies exactly
    # that filter per ref.
    refs_out = resolve_session_questionnaire_refs(db, row)
    questionnaire_title = refs_out[0]["title"] if refs_out else {}
    return SessionPublicOut(
        id=row.id,
        title=row.title,
        status=row.status,
        questionnaire_ref={"id": row.questionnaire_id, "version": row.questionnaire_version},
        default_language=row.default_language,
        facilitator_name=owner.display_name if owner else "",
        questionnaire_title=questionnaire_title,
        questionnaire_refs=refs_out,
    )


@router.get("/{session_id}")
def get_session(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    row = _get_owned_session(session_id, db, user)
    settings = get_settings()
    refs_out = resolve_session_questionnaire_refs(db, row)
    return session_to_out(row, settings.base_url, refs_out).model_dump(mode="json", by_alias=True)


@router.patch("/{session_id}")
def patch_session(
    session_id: str,
    body: SessionPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    row = _get_owned_session(session_id, db, user)
    if body.title is not None:
        row.title = body.title
    if body.status is not None:
        row.status = body.status
    if body.default_language is not None:
        row.default_language = body.default_language
    if body.questionnaire_refs is not None:
        # spec 08 §3.1/§5.7: replaceable only while the session has no FIPs.
        has_fips = db.query(Fip.id).filter(Fip.session_id == row.id).first() is not None
        if has_fips:
            raise HTTPException(status_code=409, detail="session_has_fips")
        refs_to_store, primary_id, primary_version, errors = _prepare_questionnaire_refs(
            db, user, None, body.questionnaire_refs
        )
        if errors:
            return JSONResponse(
                status_code=400, content={"detail": "invalid_content", "errors": errors}
            )
        row.questionnaire_refs = refs_to_store
        row.questionnaire_id = primary_id
        row.questionnaire_version = primary_version
    db.commit()
    db.refresh(row)
    settings = get_settings()
    refs_out = resolve_session_questionnaire_refs(db, row)
    return session_to_out(row, settings.base_url, refs_out).model_dump(mode="json", by_alias=True)


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Response:
    """Review finding 5: owner or admin only (`_get_owned_session`, same as
    every other session route). `Fip.session_id` has no `ondelete` action
    (unlike `Feedback.session_id`/`Feedback.fip_id`, which are already
    `ondelete="SET NULL"`), so a plain `db.delete(row)` here would hit an
    IntegrityError the moment any FIP still references this session -- each
    FIP is handled explicitly first: an anonymous one (never claimed,
    `owner_id IS NULL`) is deleted outright, a claimed/owned one is merely
    detached (`session_id = None`) so it survives under its owner. Feedback
    rows referencing this session or one of its now-deleted FIPs are left in
    place with their `session_id`/`fip_id` nulled by the FK's own
    `ondelete="SET NULL"`, so previously collected feedback stays readable."""
    row = _get_owned_session(session_id, db, user)
    fips = db.query(Fip).filter(Fip.session_id == row.id).all()
    for fip in fips:
        if fip.owner_id is None:
            db.delete(fip)
        else:
            fip.session_id = None
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/{session_id}/fips")
def list_session_fips(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    row = _get_owned_session(session_id, db, user)
    rows = db.query(Fip).filter(Fip.session_id == row.id).order_by(Fip.created_at).all()
    # Review finding 3: `summary.totalQuestions` was always null here --
    # fetch each distinct knowledge model referenced by these FIPs once
    # (not once per FIP) and pass its question count/ids through.
    km_cache: dict[tuple[str, str], KnowledgeModel | None] = {}
    refs = resolve_session_questionnaire_refs(db, row)
    items = []
    for f in rows:
        km_key = (f.questionnaire_id, f.questionnaire_version)
        if km_key not in km_cache:
            km_cache[km_key] = db.get(KnowledgeModel, km_key)
        km = km_cache[km_key]
        items.append(
            fip_out_dict(
                f,
                total_questions=total_questions_for_km(km),
                known_question_ids=known_question_ids_for_km(km),
                area_label=area_label_for_refs(refs, f.questionnaire_id, f.questionnaire_version),
            )
        )
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
