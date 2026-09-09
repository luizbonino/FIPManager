"""Admin-only endpoints: user management, FER promotion/merge (spec
05-v1-completion.md §1). Mounted at prefix `/admin` (then `/api` at the
main.py level), every route behind `require_admin_404` so `/api/admin/*`
never confirms its own existence to a non-admin (spec 01 §5's leak rule).
`importer.py` only ever writes `source="seed"` rows; this router is the only
writer of `source="user-promoted"`."""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from fipm.auth import hash_password, revoke_all_sessions
from fipm.authz import require_admin_404
from fipm.config import get_settings
from fipm.db import get_db
from fipm.ids import temp_password
from fipm.km_content import content_sha256
from fipm.mail import queue_mail, render_mail
from fipm.models import Fer, Fip, KnowledgeModel, User, WorkshopSession
from fipm.schemas import (
    AdminFerMergeOut,
    AdminFerMergeRequest,
    AdminFerOut,
    AdminResetPasswordOut,
    AdminUserOut,
    FerOut,
    ListOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=ListOut)
def list_users(
    q: str | None = None,
    # Review finding 12: an unclamped limit/offset lets a caller request an
    # unbounded page (limit) or a nonsensical negative offset; both are 422
    # now instead of silently doing something odd.
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_404),
) -> ListOut:
    query = db.query(User)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            (func.lower(User.email).like(like)) | (func.lower(User.display_name).like(like))
        )
    total = query.count()
    rows = query.order_by(User.created_at).offset(offset).limit(limit).all()

    # Three GROUP BY queries joined in Python, never N+1 (spec 05 §1).
    fip_counts = dict(
        db.query(Fip.owner_id, func.count(Fip.id))
        .filter(Fip.owner_id.isnot(None))
        .group_by(Fip.owner_id)
        .all()
    )
    session_counts = dict(
        db.query(WorkshopSession.owner_id, func.count(WorkshopSession.id))
        .filter(WorkshopSession.owner_id.isnot(None))
        .group_by(WorkshopSession.owner_id)
        .all()
    )
    km_counts = dict(
        db.query(KnowledgeModel.owner_id, func.count(KnowledgeModel.id))
        .filter(KnowledgeModel.owner_id.isnot(None))
        .group_by(KnowledgeModel.owner_id)
        .all()
    )

    items: list[dict[str, Any]] = [
        AdminUserOut(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            language=u.language,
            created_at=u.created_at,
            must_change_password=u.must_change_password,
            privacy_accepted_version=u.privacy_accepted_version,
            fip_count=fip_counts.get(u.id, 0),
            session_count=session_counts.get(u.id, 0),
            knowledge_model_count=km_counts.get(u.id, 0),
        ).model_dump(mode="json", by_alias=True)
        for u in rows
    ]
    return ListOut(items=items, total=total)


@router.post("/users/{user_id}/reset-password", response_model=AdminResetPasswordOut)
def reset_password(
    user_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_404),
) -> AdminResetPasswordOut:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="cannot_reset_self")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="not_found")

    plaintext = temp_password()
    user.password_hash = hash_password(plaintext)
    user.must_change_password = True
    db.commit()
    # Every pre-existing session of this user, gone -- the plaintext appears
    # in this response body and in no log line.
    revoke_all_sessions(db, user.id)

    # spec 07-mail-and-migration.md §1: the password-changed notice also
    # goes out after an admin reset, same as a self-service reset confirm.
    settings = get_settings()
    subject, text = render_mail(
        "password-changed",
        user.language,
        {
            "appName": "FIP Manager",
            "displayName": user.display_name,
            "baseUrl": settings.base_url,
            "contactEmail": settings.contact_email,
            "expiresHours": "0",
        },
    )
    queue_mail(background_tasks, user.email, subject, text)
    return AdminResetPasswordOut(temporary_password=plaintext)


def _fer_usage_counts(db: Session) -> dict[str, int]:
    """One Python pass over `db.query(Fer.answers)`-equivalent
    (`Fip.answers`): counts declarations referencing each FER by `ferId` or
    `successorFerId` (spec 05 §1 -- merge re-points both, so "usage" counts
    both), plus (review finding 2) every knowledge-model question that
    suggests it via `suggestedFerIds` (all models, all versions) -- a FER an
    editor has curated into a question's picklist is "in use" even before
    any FIP declares it, and `merge_fer` repoints exactly this same set.
    O(rows), fine at v1 scale; documented, not indexed."""
    counts: dict[str, int] = {}
    for (answers,) in db.query(Fip.answers).all():
        for answer in answers or []:
            for decl in answer.get("declarations") or []:
                for key in ("ferId", "successorFerId"):
                    fer_id = decl.get(key)
                    if fer_id:
                        counts[fer_id] = counts.get(fer_id, 0) + 1
    for (content,) in db.query(KnowledgeModel.content).all():
        for section in (content or {}).get("sections") or []:
            if not isinstance(section, dict):
                continue
            for question in section.get("questions") or []:
                if not isinstance(question, dict):
                    continue
                for fer_id in question.get("suggestedFerIds") or []:
                    if fer_id:
                        counts[fer_id] = counts.get(fer_id, 0) + 1
    return counts


def _repoint_suggested_fer_ids(db: Session, fer_id: str, target_id: str) -> int:
    """Review finding 2: `merge_fer` re-points `Fip.answers` declarations
    but, until now, left every knowledge model's `content.sections[].
    questions[].suggestedFerIds` still naming the just-deleted `fer_id` --
    a published questionnaire would keep offering an id `GET /api/fers`
    (and every other read path) no longer knows about. Walks every
    `KnowledgeModel` row (all ids, all versions), rewrites `fer_id` ->
    `target_id` wherever it appears in a question's `suggestedFerIds`
    (de-duplicating, since the question may already suggest both), and
    returns the number of rows changed."""
    changed_rows = 0
    for km in db.query(KnowledgeModel).all():
        content = copy.deepcopy(km.content or {})
        sections = content.get("sections")
        if not isinstance(sections, list):
            continue
        changed = False
        for section in sections:
            if not isinstance(section, dict):
                continue
            questions = section.get("questions")
            if not isinstance(questions, list):
                continue
            for question in questions:
                if not isinstance(question, dict):
                    continue
                suggested = question.get("suggestedFerIds")
                if not isinstance(suggested, list) or fer_id not in suggested:
                    continue
                new_suggested: list[str] = []
                for sid in suggested:
                    new_id = target_id if sid == fer_id else sid
                    if new_id not in new_suggested:
                        new_suggested.append(new_id)
                question["suggestedFerIds"] = new_suggested
                changed = True
        if changed:
            km.content = content
            km.content_sha256 = content_sha256(content)
            changed_rows += 1
    return changed_rows


@router.get("/fers", response_model=ListOut)
def list_pending_fers(
    pending: int | None = None,
    q: str | None = None,
    # Review finding 12: same clamp as list_users above.
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_404),
) -> ListOut:
    query = db.query(Fer)
    if pending:
        # Review finding 8: a promoted inlineFers row (source="model") is
        # just as much awaiting curation as a plain user submission -- an
        # admin promoting it sets source="user-promoted" via the existing
        # /promote route, same as any other pending FER.
        query = query.filter(Fer.source.in_(("user", "model")))
    if q:
        query = query.filter(Fer.label_search.ilike(f"%{q.lower()}%"))
    total = query.count()
    rows = query.order_by(Fer.type, Fer.label_search).offset(offset).limit(limit).all()

    owner_ids = {r.owner_id for r in rows if r.owner_id}
    owners = (
        {u.id: u.email for u in db.query(User).filter(User.id.in_(owner_ids)).all()}
        if owner_ids
        else {}
    )
    usage_counts = _fer_usage_counts(db)

    items: list[dict[str, Any]] = [
        AdminFerOut(
            id=r.id,
            label=r.label,
            type=r.type,
            homepage=r.homepage,
            source=r.source,
            owner_email=owners.get(r.owner_id),
            usage_count=usage_counts.get(r.id, 0),
        ).model_dump(mode="json", by_alias=True)
        for r in rows
    ]
    return ListOut(items=items, total=total)


@router.post("/fers/{fer_id:path}/promote", response_model=FerOut)
def promote_fer(
    fer_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_404),
) -> FerOut:
    fer = db.get(Fer, fer_id)
    if fer is None:
        raise HTTPException(status_code=404, detail="not_found")
    if fer.source in ("seed", "user-promoted"):
        raise HTTPException(status_code=409, detail="not_promotable")

    # Label/type/homepage untouched.
    fer.owner_id = None
    fer.source = "user-promoted"
    db.commit()
    db.refresh(fer)
    return FerOut.model_validate(fer)


@router.post("/fers/{fer_id:path}/merge", response_model=AdminFerMergeOut)
def merge_fer(
    fer_id: str,
    body: AdminFerMergeRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_404),
) -> AdminFerMergeOut:
    if body.target_fer_id == fer_id:
        raise HTTPException(status_code=400, detail="same_fer")

    source = db.get(Fer, fer_id)
    if source is None:
        raise HTTPException(status_code=404, detail="not_found")
    # Review finding 4: a "seed" FER is the FIP ontology's own curated
    # registry entry (loaded by the importer, never user-submitted) --
    # merging it away would delete canonical data every re-import would
    # otherwise recreate, and there is no separate delete route for FERs to
    # protect it from either.
    if source.source == "seed":
        raise HTTPException(status_code=409, detail="seed_fer_protected")

    target = db.get(Fer, body.target_fer_id)
    if (
        target is None
        or target.source not in ("seed", "user-promoted")
        # Review finding 4: merging into a target of a different FER type
        # would silently change what every repointed declaration asserts
        # (e.g. a metadata-schema declaration repointed at an
        # identifier-service).
        or target.type != source.type
    ):
        raise HTTPException(status_code=409, detail="invalid_merge_target")

    repointed_declarations = 0
    repointed_fips = 0
    for fip in db.query(Fip).all():
        changed = False
        # A copy, not the ORM-tracked list itself: mutating fip.answers in
        # place wouldn't mark the JSON column dirty, so the row must be
        # reassigned (matches routers/fips.py's PATCH handler).
        new_answers = copy.deepcopy(fip.answers or [])
        for answer in new_answers:
            for decl in answer.get("declarations") or []:
                for key in ("ferId", "successorFerId"):
                    if decl.get(key) == fer_id:
                        decl[key] = target.id
                        repointed_declarations += 1
                        changed = True
        if changed:
            fip.answers = new_answers
            repointed_fips += 1

    repointed_knowledge_models = _repoint_suggested_fer_ids(db, fer_id, target.id)

    db.delete(source)
    db.commit()
    return AdminFerMergeOut(
        repointed_declarations=repointed_declarations,
        repointed_fips=repointed_fips,
        repointed_knowledge_models=repointed_knowledge_models,
    )
