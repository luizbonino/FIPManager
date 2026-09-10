from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fipm.authz import optional_user, require_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.fer_types import allowed_fer_type_keys
from fipm.models import Fer, User
from fipm.schemas import FerCreateRequest, FerOut, ListOut

router = APIRouter(prefix="/fers", tags=["fers"])


@router.get("", response_model=ListOut)
def list_fers(
    type: str | None = None,
    q: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> ListOut:
    # spec 05-v1-completion.md §1: a promoted FER (source="user-promoted") is
    # catalogue content, globally visible like a seed FER. spec
    # 08-workshop-picklists.md §1.3/§5.3: source="model" (an inlineFers
    # promotion) joins that globally-visible set too, anonymous callers
    # included -- a workshop participant has no account and must still see
    # the options their model suggests. spec 11-nanopub-network.md §3.6: a
    # FER row created by "use as starting point" (source="network") is the
    # same kind of globally-visible catalogue content.
    query = db.query(Fer)
    if user is not None:
        query = query.filter(
            (Fer.source.in_(("seed", "user-promoted", "model", "network")))
            | (Fer.owner_id == user.id)
        )
    else:
        query = query.filter(Fer.source.in_(("seed", "user-promoted", "model", "network")))
    if type:
        query = query.filter(Fer.type == type)
    if source:
        query = query.filter(Fer.source == source)
    if q:
        query = query.filter(Fer.label_search.ilike(f"%{q.lower()}%"))
    total = query.count()
    rows = query.order_by(Fer.type, Fer.label_search).offset(offset).limit(limit).all()
    items: list[dict[str, Any]] = [
        FerOut.model_validate(r).model_dump(mode="json", by_alias=True) for r in rows
    ]
    return ListOut(items=items, total=total)


@router.post("", response_model=FerOut, status_code=201)
def create_fer(
    body: FerCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> FerOut:
    settings = get_settings()
    allowed_types = allowed_fer_type_keys(settings)
    if allowed_types and body.type not in allowed_types:
        raise HTTPException(status_code=400, detail="invalid_fer_type")

    existing = db.get(Fer, body.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="fer_exists")

    label_search = "|".join(str(v).lower() for v in body.label.values())
    row = Fer(
        id=body.id,
        label=body.label,
        label_search=label_search,
        type=body.type,
        homepage=body.homepage,
        owner_id=user.id,
        source="user",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FerOut.model_validate(row)
