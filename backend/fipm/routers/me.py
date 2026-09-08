from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fipm.authz import require_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.schemas import KnowledgeModelSummary, ListOut, fip_out_dict, session_to_out

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/fips", response_model=ListOut)
def my_fips(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ListOut:
    query = db.query(Fip).filter(Fip.owner_id == user.id)
    if q:
        query = query.filter(Fip.title.ilike(f"%{q}%"))
    total = query.count()
    rows = query.order_by(Fip.updated_at.desc()).offset(offset).limit(limit).all()
    items = [fip_out_dict(r) for r in rows]
    return ListOut(items=items, total=total)


@router.get("/sessions", response_model=ListOut)
def my_sessions(db: Session = Depends(get_db), user: User = Depends(require_user)) -> ListOut:
    settings = get_settings()
    rows = (
        db.query(WorkshopSession)
        .filter(WorkshopSession.owner_id == user.id)
        .order_by(WorkshopSession.created_at.desc())
        .all()
    )
    items = [
        session_to_out(r, settings.base_url).model_dump(mode="json", by_alias=True) for r in rows
    ]
    return ListOut(items=items, total=len(items))


@router.get("/knowledge-models", response_model=ListOut)
def my_knowledge_models(
    db: Session = Depends(get_db), user: User = Depends(require_user)
) -> ListOut:
    rows = db.query(KnowledgeModel).filter(KnowledgeModel.owner_id == user.id).all()
    items = [
        KnowledgeModelSummary.model_validate(r).model_dump(mode="json", by_alias=True) for r in rows
    ]
    return ListOut(items=items, total=len(items))
