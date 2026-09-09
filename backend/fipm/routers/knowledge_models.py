"""Knowledge-model CRUD + lifecycle (spec 04-knowledge-model-editor.md §3)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import (
    can_read,
    can_write_owned,
    check_email_verification_gate,
    optional_user,
    require_user,
)
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

# spec 04 §1: MODEL_ID_PATTERN is `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$`, so a
# valid id is at most 1 + 62 + 1 = 64 characters.
MODEL_ID_MAX_LEN = 64


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _etag(sha256: str) -> str:
    return f'"{sha256}"'


def _commit_or_id_taken(db: Session, row: KnowledgeModel) -> None:
    """Review finding 13: `_id_in_use`'s pre-insert check is TOCTOU-racy (two
    concurrent requests can both pass it for the same id/version before
    either commits). Catch the resulting IntegrityError here instead of
    letting it surface as an unhandled 500."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="model_id_taken") from exc


def _km_out(row: KnowledgeModel) -> dict[str, Any]:
    return KnowledgeModelOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _invalid_content_response(errors: list[ContentError]) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": "invalid_content", "errors": errors})


def _id_in_use(db: Session, km_id: str) -> bool:
    return db.query(KnowledgeModel.id).filter(KnowledgeModel.id == km_id).first() is not None


def _default_model_id(db: Session, base: str, *, suffix: str | None) -> str:
    """spec 04 §1: `<base>[-suffix]`, then `-2`, `-3`, ... appended.

    Review finding 10: `base` may itself be close to MODEL_ID_MAX_LEN (a
    fork's default id starts from the source's own, already-validated, up to
    64-char id), so appending `-<suffix>[-<n>]` can overflow the pattern's
    max length. Trim `base` (never the suffix/counter, which is what makes
    the id unique) so the composed candidate always fits.
    """

    def _candidate(n: int | None) -> str:
        tail = f"-{suffix}" if suffix else ""
        if n is not None:
            tail += f"-{n}"
        max_base_len = max(MODEL_ID_MAX_LEN - len(tail), 1)
        return f"{base[:max_base_len]}{tail}"[:MODEL_ID_MAX_LEN]

    candidate = _candidate(None)
    if not _id_in_use(db, candidate):
        return candidate
    n = 2
    while True:
        candidate = _candidate(n)
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


def _is_canonical_semver_part(part: str) -> bool:
    """Digits only, no leading zero unless the part is exactly "0" (review
    finding 9): "01.0.0" must not parse as 1.0.0."""
    return part.isdigit() and (part == "0" or part[0] != "0")


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(_is_canonical_semver_part(p) for p in parts):
        raise HTTPException(status_code=400, detail="invalid_version")
    a, b, c = parts
    return int(a), int(b), int(c)


def _semver_sort_key(version: str) -> tuple[int, int, int]:
    """Like `_parse_semver`, but for read-path sorting: a malformed/legacy
    version must not 500 the whole `list_versions` response, so it sorts
    last instead."""
    try:
        return _parse_semver(version)
    except HTTPException:
        return (-1, -1, -1)


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
    # Review finding 9: newest version first, not insertion/pk order.
    visible.sort(key=lambda r: _semver_sort_key(r.version), reverse=True)
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
    _commit_or_id_taken(db, row)
    db.refresh(row)
    return _km_out(row)


@router.post("/import", status_code=201)
async def import_knowledge_model(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Any:
    settings = get_settings()
    raw = await request.body()
    # The BodySizeLimitMiddleware (fipm.main) already rejects an oversized
    # body under /api/ before/while it is read; this is a fallback in case
    # that middleware is ever bypassed or misconfigured (review finding 3).
    if len(raw) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="payload_too_large")
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        # ValueError covers json.JSONDecodeError; RecursionError is raised by
        # the stdlib json decoder on deeply nested input, which is not a
        # ValueError (review finding 2) -- both are a malformed request body,
        # not a server error.
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    try:
        body = KnowledgeModelImportRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="validation_error") from exc

    document = body.document
    if not isinstance(document, dict):
        raise HTTPException(status_code=400, detail="invalid_document")

    # Review finding 4: pass the document's own title/description/sections
    # through unchanged (only filling in an *absent* key), instead of
    # silently coercing a wrong-typed value to an empty default -- so
    # `validate_content` catches the type mismatch and reports 400
    # `invalid_content` instead of quietly creating an empty model. `title`
    # is coerced to a dict only for the id-slug fallback below, which must
    # not crash on a wrong-typed title.
    title = document.get("title")
    if title is None:
        title = {}
    title_for_slug = title if isinstance(title, dict) else {}
    description = document.get("description")
    if description is None:
        description = deepcopy(title)
    sections = document.get("sections")
    if sections is None:
        sections = []
    changelog = document.get("changelog")
    if changelog is None:
        changelog = []
    license_ = document.get("license") or "CC0-1.0"
    source_val = document.get("source") if document.get("source") is not None else "FIP Manager"

    if body.id:
        _validate_caller_id(db, body.id)
        km_id = body.id
    else:
        km_id = _default_model_id(db, _slug_base(title_for_slug), suffix=None)

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
    # Review finding 6: round-tripping an exported fork (whose document
    # carries `attribution`/`forkedFrom` inside `content`) through import
    # must keep them, not silently drop them.
    if "attribution" in document:
        content["attribution"] = document["attribution"]
    if "forkedFrom" in document:
        content["forkedFrom"] = document["forkedFrom"]

    errors = validate_content(content, settings=settings)
    if not isinstance(changelog, list):
        # validate_content (km_content.py) has no opinion on `changelog`
        # (spec 04 §3.3 doesn't list it), so a wrong-typed value is checked
        # here directly -- same finding-4 rationale, applied to the one
        # content field validate_content doesn't cover.
        errors.append(
            {"path": "changelog", "code": "missing_key", "message": "changelog must be a list"}
        )
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
    _commit_or_id_taken(db, row)
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
    # Review finding 5: content.license must mirror the row's final licence
    # in both branches -- the deep-copied source content could otherwise
    # carry a stale/differently-formatted licence string.
    content["license"] = license_

    if body.new_id:
        _validate_caller_id(db, body.new_id)
        new_id = body.new_id
    else:
        new_id = _default_model_id(db, source.id, suffix="fork")

    # Review finding 11 / spec 04 §1: all three ways a user model starts
    # (fork, scratch, import) create it at version "1.0.0", not the source's
    # version -- the fork request has no way to ask for anything else.
    new_version = "1.0.0"
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
    _commit_or_id_taken(db, row)
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

    if body.visibility is not None:
        check_email_verification_gate(user, body.visibility)

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
    response = JSONResponse(status_code=200, content=_km_out(row))
    if content_changed:
        # Review finding 7: title/description live inside `content` (they're
        # mirrored into it above), so a metadata PATCH that touches either
        # one does legitimately change content_sha256 -- surface the new
        # ETag rather than silently recomputing it with no way for the
        # caller to learn the new value (e.g. before a subsequent PUT
        # .../content, which requires If-Match).
        response.headers["ETag"] = _etag(row.content_sha256)
    return response


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
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Any:
    settings = get_settings()
    row = _get_owned_km_or_404(db, km_id, version, user)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="model_published")
    # Review finding 13: If-Match is optional here (unlike PUT .../content,
    # where it's required) -- a caller that has an ETag from a prior GET/PUT
    # can still catch "someone else edited this draft after I loaded it, and
    # I'm about to publish over their change" before it becomes irreversible.
    if if_match is not None:
        current_etag = _etag(row.content_sha256)
        if if_match != current_etag:
            return JSONResponse(
                status_code=409, content={"detail": "content_conflict", "etag": current_etag}
            )
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

    # Review finding 9: bump from the highest version this model id already
    # has (not necessarily `row.version` -- new-version can be called again
    # on an older published version once its own successor is deleted, or
    # while other published versions coexist), so the default bump can't
    # collide with one of them.
    version_rows = db.query(KnowledgeModel.version).filter(KnowledgeModel.id == km_id).all()
    existing_versions = [v for (v,) in version_rows]

    if body.version:
        new_version = body.version
        if _parse_semver(new_version) <= _parse_semver(row.version):
            raise HTTPException(status_code=400, detail="version_not_greater")
    else:
        highest = max(existing_versions, key=_parse_semver)
        new_version = _bump_semver(highest, body.bump or "minor")

    # Review finding 1: check the (id, new_version) collision up front and
    # return 409 `version_exists` instead of letting it fall through to an
    # unhandled IntegrityError (500) at commit time.
    if new_version in existing_versions:
        raise HTTPException(status_code=409, detail="version_exists")

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
