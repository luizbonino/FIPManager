from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fipm.authz import can_read, optional_user, require_user
from fipm.db import get_db
from fipm.models import KnowledgeModel, User
from fipm.schemas import (
    KnowledgeModelOut,
    KnowledgeModelSummary,
    KnowledgeModelVersionEntry,
    ListOut,
)

router = APIRouter(prefix="/knowledge-models", tags=["knowledge-models"])


@router.get("", response_model=ListOut)
def list_knowledge_models(
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> ListOut:
    query = db.query(KnowledgeModel)
    if user is not None:
        query = query.filter(
            ((KnowledgeModel.visibility == "public") & (KnowledgeModel.status == "published"))
            | (KnowledgeModel.owner_id == user.id)
        )
    else:
        query = query.filter(
            KnowledgeModel.visibility == "public", KnowledgeModel.status == "published"
        )
    if status:
        query = query.filter(KnowledgeModel.status == status)
    if q:
        query = query.filter(KnowledgeModel.id.ilike(f"%{q}%"))
    rows = query.order_by(KnowledgeModel.id, KnowledgeModel.version).all()
    items = [
        KnowledgeModelSummary.model_validate(r).model_dump(mode="json", by_alias=True) for r in rows
    ]
    return ListOut(items=items, total=len(items))


@router.get("/{km_id}/versions", response_model=ListOut)
def list_versions(
    km_id: str, db: Session = Depends(get_db), user: User | None = Depends(optional_user)
) -> ListOut:
    rows = db.query(KnowledgeModel).filter(KnowledgeModel.id == km_id).all()
    visible = [r for r in rows if can_read(r.owner_id, r.visibility, user)]
    if not visible:
        raise HTTPException(status_code=404, detail="not_found")
    items = [
        KnowledgeModelVersionEntry(
            version=r.version, status=r.status, changelog=r.changelog or []
        ).model_dump(mode="json", by_alias=True)
        for r in visible
    ]
    return ListOut(items=items, total=len(items))


@router.get("/{km_id}/{version}", response_model=KnowledgeModelOut)
def get_knowledge_model(
    km_id: str,
    version: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> KnowledgeModelOut:
    row = db.get(KnowledgeModel, (km_id, version))
    if row is None or not can_read(row.owner_id, row.visibility, user):
        raise HTTPException(status_code=404, detail="not_found")
    return KnowledgeModelOut.model_validate(row)


# --- Week-3 scope (spec §6): stubs so the route table matches the spec. ---


@router.post("", status_code=501)
def create_knowledge_model(user: User = Depends(require_user)) -> None:
    raise HTTPException(status_code=501, detail="not_implemented")


@router.post("/import", status_code=501)
def import_knowledge_model(user: User = Depends(require_user)) -> None:
    raise HTTPException(status_code=501, detail="not_implemented")


@router.post("/{km_id}/{version}/fork", status_code=501)
def fork_knowledge_model(km_id: str, version: str, user: User = Depends(require_user)) -> None:
    raise HTTPException(status_code=501, detail="not_implemented")


@router.patch("/{km_id}/{version}", status_code=501)
def patch_knowledge_model(km_id: str, version: str, user: User = Depends(require_user)) -> None:
    raise HTTPException(status_code=501, detail="not_implemented")


@router.post("/{km_id}/{version}/publish", status_code=501)
def publish_knowledge_model(km_id: str, version: str, user: User = Depends(require_user)) -> None:
    raise HTTPException(status_code=501, detail="not_implemented")
