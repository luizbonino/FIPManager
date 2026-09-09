"""Admin-only endpoints: user management, FER promotion/merge (spec
05-v1-completion.md §1). Mounted at prefix `/admin` (then `/api` at the
main.py level), every route behind `require_admin_404` so `/api/admin/*`
never confirms its own existence to a non-admin (spec 01 §5's leak rule).
`importer.py` only ever writes `source="seed"` rows; this router is the only
writer of `source="user-promoted"`."""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from fipm.auth import hash_password, revoke_all_sessions
from fipm.authz import require_admin_404
from fipm.db import get_db
from fipm.ids import temp_password
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
    limit: int = 50,
    offset: int = 0,
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
    return AdminResetPasswordOut(temporary_password=plaintext)


def _fer_usage_counts(db: Session) -> dict[str, int]:
    """One Python pass over `db.query(Fer.answers)`-equivalent
    (`Fip.answers`): counts declarations referencing each FER by `ferId` or
    `successorFerId` (spec 05 §1 -- merge re-points both, so "usage" counts
    both). O(rows), fine at v1 scale; documented, not indexed."""
    counts: dict[str, int] = {}
    for (answers,) in db.query(Fip.answers).all():
        for answer in answers or []:
            for decl in answer.get("declarations") or []:
                for key in ("ferId", "successorFerId"):
                    fer_id = decl.get(key)
                    if fer_id:
                        counts[fer_id] = counts.get(fer_id, 0) + 1
    return counts


@router.get("/fers", response_model=ListOut)
def list_pending_fers(
    pending: int | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_404),
) -> ListOut:
    query = db.query(Fer)
    if pending:
        query = query.filter(Fer.source == "user")
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

    target = db.get(Fer, body.target_fer_id)
    if target is None or target.source not in ("seed", "user-promoted"):
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

    db.delete(source)
    db.commit()
    return AdminFerMergeOut(
        repointed_declarations=repointed_declarations, repointed_fips=repointed_fips
    )
