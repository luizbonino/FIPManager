"""Knowledge-model CRUD + lifecycle (spec 04-knowledge-model-editor.md §3)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from fipm.authz import can_read, can_write_owned, optional_user, require_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.km_content import (
    MODEL_ID_PATTERN,
    ContentError,
    content_sha256,
    normalize_source,
    random_id_base,
    slugify,
    validate_content,
    validate_langmap,
)
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.schemas import (
    KnowledgeModelContentPutRequest,
    KnowledgeModelCreateRequest,
    KnowledgeModelForkRequest,
    KnowledgeModelImportRequest,
    KnowledgeModelNewVersionRequest,
    KnowledgeModelOut,
    KnowledgeModelPatchRequest,
    KnowledgeModelPublishRequest,
    KnowledgeModelVersionEntry,
    ListOut,
    km_summary_dict,
)

router = APIRouter(prefix="/knowledge-models", tags=["knowledge-models"])

IMPORT_MAX_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _etag(sha256: str) -> str:
    return f'"{sha256}"'


def _km_out(row: KnowledgeModel) -> dict[str, Any]:
    return KnowledgeModelOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _invalid_content_response(errors: list[ContentError]) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": "invalid_content", "errors": errors})


def _id_in_use(db: Session, km_id: str) -> bool:
    return db.query(KnowledgeModel.id).filter(KnowledgeModel.id == km_id).first() is not None


def _default_model_id(db: Session, base: str, *, suffix: str | None) -> str:
    """spec 04 §1: `<base>[-suffix]`, then `-2`, `-3`, ... appended."""
    candidate = f"{base}-{suffix}" if suffix else base
    if not _id_in_use(db, candidate):
        return candidate
    n = 2
    while True:
        candidate = f"{base}-{suffix}-{n}" if suffix else f"{base}-{n}"
        if not _id_in_use(db, candidate):
            return candidate
        n += 1


def _slug_base(title: dict[str, Any] | None) -> str:
    slug = slugify((title or {}).get("en") or "")
    return slug or f"model-{random_id_base()}"


def _validate_caller_id(db: Session, km_id: str) -> None:
    if not MODEL_ID_PATTERN.match(km_id):
        raise HTTPException(status_code=400, detail="invalid_id")
    if _id_in_use(db, km_id):
        raise HTTPException(status_code=409, detail="model_id_taken")


def _get_readable_km_or_404(
    db: Session, km_id: str, version: str, user: User | None
) -> KnowledgeModel:
    row = db.get(KnowledgeModel, (km_id, version))
    if row is None or not can_read(row.owner_id, row.visibility, user):
        raise HTTPException(status_code=404, detail="not_found")
    return row


def _get_owned_km_or_404(db: Session, km_id: str, version: str, user: User) -> KnowledgeModel:
    """404 unreadable; 403 system_model_readonly for a system row (no admin
    exception -- spec 04 §7 A2: never editable in place, not even by an
    admin, through this API); 403 forbidden readable-but-not-owned."""
    row = _get_readable_km_or_404(db, km_id, version, user)
    if row.owner_id is None:
        raise HTTPException(status_code=403, detail="system_model_readonly")
    if not can_write_owned(row.owner_id, user):
        raise HTTPException(status_code=403, detail="forbidden")
    return row


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise HTTPException(status_code=400, detail="invalid_version")
    a, b, c = parts
    return int(a), int(b), int(c)


def _bump_semver(version: str, bump: str) -> str:
    major, minor, patch = _parse_semver(version)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


# ---------------------------------------------------------------------------
# Read routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ListOut)
def list_knowledge_models(
    status: str | None = None,
    q: str | None = None,
    mine: bool = False,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> ListOut:
    if mine:
        if user is None:
            return ListOut(items=[], total=0)
        query = db.query(KnowledgeModel).filter(KnowledgeModel.owner_id == user.id)
    else:
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
    items = [km_summary_dict(r) for r in rows]
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
    response: Response,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> KnowledgeModelOut:
    row = _get_readable_km_or_404(db, km_id, version, user)
    response.headers["ETag"] = _etag(row.content_sha256)
    return KnowledgeModelOut.model_validate(row)


@router.get("/{km_id}/{version}/export.json")
def export_knowledge_model_json(
    km_id: str,
    version: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    row = _get_readable_km_or_404(db, km_id, version, user)
    content = dict(row.content or {})
    content.update(
        {
            "id": row.id,
            "version": row.version,
            "status": row.status,
            "license": row.license,
            "source": content.get("source", row.source),
            "title": row.title,
            "description": row.description,
            "changelog": row.changelog or [],
            "sections": content.get("sections", []),
        }
    )
    return Response(
        content=json.dumps(content, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{row.id}-{row.version}.json"'},
    )


# ---------------------------------------------------------------------------
# Creation routes: from scratch, import, fork
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def create_knowledge_model(
    body: KnowledgeModelCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    settings = get_settings()
    title = body.title
    description = body.description if body.description is not None else deepcopy(title)
    sections = body.sections if body.sections is not None else []
    license_ = body.license or "CC0-1.0"

    if body.id:
        _validate_caller_id(db, body.id)
        km_id = body.id
    else:
        km_id = _default_model_id(db, _slug_base(title), suffix=None)

    content = {
        "id": km_id,
        "version": "1.0.0",
        "status": "draft",
        "license": license_,
        "source": "FIP Manager",
        "title": title,
        "description": description,
        "changelog": [],
        "sections": sections,
    }
    errors = validate_content(content, settings=settings)
    if errors:
        return _invalid_content_response(errors)

    row = KnowledgeModel(
        id=km_id,
        version="1.0.0",
        owner_id=user.id,
        visibility="private",
        status="draft",
        license=license_,
        source="FIP Manager",
        title=title,
        description=description,
        changelog=[],
        content=content,
        content_sha256=content_sha256(content),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _km_out(row)


@router.post("/import", status_code=201)
async def import_knowledge_model(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Any:
    settings = get_settings()
    raw = await request.body()
    if len(raw) > IMPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="payload_too_large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    try:
        body = KnowledgeModelImportRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="validation_error") from exc

    document = body.document
    if not isinstance(document, dict):
        raise HTTPException(status_code=400, detail="invalid_document")

    title = document.get("title") if isinstance(document.get("title"), dict) else {}
    description = (
        document.get("description")
        if isinstance(document.get("description"), dict)
        else deepcopy(title)
    )
    sections = document.get("sections") if isinstance(document.get("sections"), list) else []
    license_ = document.get("license") or "CC0-1.0"
    source_val = document.get("source") if document.get("source") is not None else "FIP Manager"
    changelog = document.get("changelog") if isinstance(document.get("changelog"), list) else []

    if body.id:
        _validate_caller_id(db, body.id)
        km_id = body.id
    else:
        km_id = _default_model_id(db, _slug_base(title), suffix=None)

    content = {
        "id": km_id,
        "version": "1.0.0",
        "status": "draft",
        "license": license_,
        "source": source_val,
        "title": title,
        "description": description,
        "changelog": changelog,
        "sections": sections,
    }
    errors = validate_content(content, settings=settings)
    if errors:
        return _invalid_content_response(errors)

    row = KnowledgeModel(
        id=km_id,
        version="1.0.0",
        owner_id=user.id,
        visibility="private",
        status="draft",
        license=license_,
        source=normalize_source(source_val),
        title=title,
        description=description,
        changelog=changelog,
        content=content,
        content_sha256=content_sha256(content),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _km_out(row)


# spec 00-fip-ontology-mapping.md §6: required attribution string for a
# CC-BY-SA-4.0-derived questionnaire.
FORK_CC_BY_SA_ATTRIBUTION = (
    "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, "
    "Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."
)


@router.post("/{km_id}/{version}/fork", status_code=201)
def fork_knowledge_model(
    km_id: str,
    version: str,
    body: KnowledgeModelForkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    settings = get_settings()
    source = _get_readable_km_or_404(db, km_id, version, user)

    content = deepcopy(source.content or {})
    content["changelog"] = []
    content["forkedFrom"] = {"id": source.id, "version": source.version}
    title = body.title if body.title is not None else deepcopy(source.title)
    description = deepcopy(source.description)
    content["title"] = title
    content["description"] = description

    license_ = source.license
    if (source.license or "").startswith("CC-BY-SA"):
        license_ = "CC-BY-SA-4.0"
        content["attribution"] = FORK_CC_BY_SA_ATTRIBUTION
    # else: licence and content["source"] (already deep-copied) pass through
    # unchanged, per spec 04 §1.

    if body.new_id:
        _validate_caller_id(db, body.new_id)
        new_id = body.new_id
    else:
        new_id = _default_model_id(db, source.id, suffix="fork")

    new_version = source.version
    content["id"] = new_id
    content["version"] = new_version
    content["status"] = "draft"

    errors = validate_content(content, settings=settings)
    if errors:
        return _invalid_content_response(errors)

    row = KnowledgeModel(
        id=new_id,
        version=new_version,
        owner_id=user.id,
        visibility="private",
        status="draft",
        license=license_,
        source=source.source,
        title=title,
        description=description,
        changelog=[],
        content=content,
        content_sha256=content_sha256(content),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _km_out(row)


# ---------------------------------------------------------------------------
# Draft editing: PATCH metadata, PUT content
# ---------------------------------------------------------------------------


@router.patch("/{km_id}/{version}")
def patch_knowledge_model(
    km_id: str,
    version: str,
    body: KnowledgeModelPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    row = _get_readable_km_or_404(db, km_id, version, user)

    if row.owner_id is None:
        # spec 04 §7 A2: system models take admin writes for visibility only.
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="system_model_readonly")
        if body.title is not None or body.description is not None:
            raise HTTPException(status_code=403, detail="system_model_readonly")
        if body.visibility is not None:
            row.visibility = body.visibility
            db.commit()
            db.refresh(row)
        return _km_out(row)

    if not can_write_owned(row.owner_id, user):
        raise HTTPException(status_code=403, detail="forbidden")

    if row.status == "published":
        if body.title is not None or body.description is not None:
            raise HTTPException(status_code=409, detail="model_published")
        if body.visibility is not None:
            row.visibility = body.visibility
            db.commit()
            db.refresh(row)
        return _km_out(row)

    errors: list[ContentError] = []
    if body.title is not None:
        errors += validate_langmap(body.title, "title")
    if body.description is not None:
        errors += validate_langmap(body.description, "description")
    if errors:
        return _invalid_content_response(errors)

    content_changed = body.title is not None or body.description is not None
    if content_changed:
        content = dict(row.content or {})
        if body.title is not None:
            row.title = body.title
            content["title"] = body.title
        if body.description is not None:
            row.description = body.description
            content["description"] = body.description
        row.content = content
        row.content_sha256 = content_sha256(content)
    if body.visibility is not None:
        row.visibility = body.visibility

    db.commit()
    db.refresh(row)
    return _km_out(row)


@router.put("/{km_id}/{version}/content")
def put_knowledge_model_content(
    km_id: str,
    version: str,
    body: KnowledgeModelContentPutRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    settings = get_settings()
    row = _get_owned_km_or_404(db, km_id, version, user)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="model_published")

    if if_match is None:
        raise HTTPException(status_code=428, detail="if_match_required")

    current_etag = _etag(row.content_sha256)
    if if_match != current_etag:
        return JSONResponse(
            status_code=409, content={"detail": "content_conflict", "etag": current_etag}
        )

    content = dict(row.content or {})
    content["sections"] = body.sections
    if body.title is not None:
        content["title"] = body.title
    if body.description is not None:
        content["description"] = body.description
    content["id"] = row.id
    content["version"] = row.version
    content["status"] = row.status

    errors = validate_content(content, settings=settings)
    if errors:
        return _invalid_content_response(errors)

    row.content = content
    if body.title is not None:
        row.title = body.title
    if body.description is not None:
        row.description = body.description
    row.content_sha256 = content_sha256(content)
    db.commit()
    db.refresh(row)

    response = JSONResponse(status_code=200, content=_km_out(row))
    response.headers["ETag"] = _etag(row.content_sha256)
    return response


# ---------------------------------------------------------------------------
# Lifecycle: publish, new-version, delete
# ---------------------------------------------------------------------------


@router.post("/{km_id}/{version}/publish")
def publish_knowledge_model(
    km_id: str,
    version: str,
    body: KnowledgeModelPublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    settings = get_settings()
    row = _get_owned_km_or_404(db, km_id, version, user)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="model_published")
    if not body.notes or not body.notes.strip():
        raise HTTPException(status_code=400, detail="changelog_notes_required")

    content = dict(row.content or {})
    errors = validate_content(content, publishing=True, settings=settings)
    if errors:
        return _invalid_content_response(errors)

    entry = {
        "version": row.version,
        "date": datetime.now(UTC).date().isoformat(),
        "notes": body.notes,
    }
    changelog = [*(row.changelog or []), entry]
    content["changelog"] = changelog
    content["status"] = "published"

    row.changelog = changelog
    row.status = "published"
    row.content = content
    row.content_sha256 = content_sha256(content)
    db.commit()
    db.refresh(row)
    return _km_out(row)


@router.post("/{km_id}/{version}/new-version", status_code=201)
def new_knowledge_model_version(
    km_id: str,
    version: str,
    body: KnowledgeModelNewVersionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    row = _get_owned_km_or_404(db, km_id, version, user)
    if row.status != "published":
        raise HTTPException(status_code=409, detail="not_published")

    existing_draft = (
        db.query(KnowledgeModel)
        .filter(KnowledgeModel.id == km_id, KnowledgeModel.status == "draft")
        .first()
    )
    if existing_draft is not None:
        raise HTTPException(status_code=409, detail="draft_exists")

    if body.version:
        new_version = body.version
        if _parse_semver(new_version) <= _parse_semver(row.version):
            raise HTTPException(status_code=400, detail="version_not_greater")
    else:
        new_version = _bump_semver(row.version, body.bump or "minor")

    content = deepcopy(row.content or {})
    content["version"] = new_version
    content["status"] = "draft"

    new_row = KnowledgeModel(
        id=km_id,
        version=new_version,
        owner_id=row.owner_id,
        visibility=row.visibility,
        status="draft",
        license=row.license,
        source=row.source,
        title=row.title,
        description=row.description,
        changelog=row.changelog or [],
        content=content,
        content_sha256=content_sha256(content),
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return _km_out(new_row)


@router.delete("/{km_id}/{version}", status_code=204)
def delete_knowledge_model(
    km_id: str,
    version: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    row = _get_owned_km_or_404(db, km_id, version, user)
    if row.status == "draft":
        db.delete(row)
        db.commit()
        return

    in_use = (
        db.query(Fip.id)
        .filter(Fip.questionnaire_id == km_id, Fip.questionnaire_version == version)
        .first()
        is not None
        or db.query(WorkshopSession.id)
        .filter(
            WorkshopSession.questionnaire_id == km_id,
            WorkshopSession.questionnaire_version == version,
        )
        .first()
        is not None
    )
    if in_use:
        raise HTTPException(status_code=409, detail="model_in_use")
    db.delete(row)
    db.commit()
