from __future__ import annotations

import copy
import json
import secrets
from datetime import UTC, datetime
from typing import Any, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fipm.authz import (
    can_read,
    can_write_owned,
    check_edit_token,
    check_email_verification_gate,
    get_readable_published_km,
    optional_user,
    require_user,
)
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.dmp import apply_dmp_evidence, normalise_legacy_dmp_evidence, normalise_related_dmps
from fipm.exporters import (
    build_export_csv,
    build_export_json,
    reconstruct_answers_from_export,
    reconstruct_orphaned_answers_from_export,
)
from fipm.ids import hash_token, new_token, short_id
from fipm.migration import (
    MigrationError,
    apply_migration,
    changelog_between,
    compute_diff,
    semver_gt,
    semver_key,
)
from fipm.models import Fip, KnowledgeModel, User, WorkshopSession
from fipm.rdf import fip_graph, orphaned_answer_comment_lines, to_jsonld, to_turtle
from fipm.schemas import (
    Answer,
    FipCreateRequest,
    FipImportDoc,
    FipPatchRequest,
    Language,
    MigratedFromImport,
    MigrateRequest,
    OrphanedAnswerImport,
    PrefillFromDmpRequest,
    Visibility,
    answer_dump,
    area_label_for_refs,
    fip_out_dict,
    known_question_ids_for_km,
    session_questionnaire_refs,
    total_questions_for_km,
)

router = APIRouter(prefix="/fips", tags=["fips"])


def _out(
    fip: Fip,
    edit_token: str | None = None,
    total_questions: int | None = None,
    known_question_ids: set[str] | None = None,
    area_label: dict[str, str] | None = None,
) -> dict[str, Any]:
    return fip_out_dict(
        fip,
        edit_token,
        total_questions=total_questions,
        known_question_ids=known_question_ids,
        area_label=area_label,
    )


def _area_label_for_fip(db: Session, fip: Fip) -> dict[str, str] | None:
    """spec 08-workshop-picklists.md §3.2: `FipOut.areaLabel` -- non-null
    only for a FIP in a multi-ref session, looked up from the session's ref
    list at read/export time (never copied onto the FIP row) so a label fix
    propagates."""
    if fip.session_id is None:
        return None
    session_row = db.get(WorkshopSession, fip.session_id)
    if session_row is None:
        return None
    refs = session_questionnaire_refs(session_row)
    return area_label_for_refs(refs, fip.questionnaire_id, fip.questionnaire_version)


def _out_for_km(
    fip: Fip, km: KnowledgeModel | None, db: Session, edit_token: str | None = None
) -> dict[str, Any]:
    """`_out`, deriving `total_questions`/`known_question_ids`/`area_label`
    from `km`/`db` in one place (review findings 3/5)."""
    return _out(
        fip,
        edit_token,
        total_questions=total_questions_for_km(km),
        known_question_ids=known_question_ids_for_km(km),
        area_label=_area_label_for_fip(db, fip),
    )


def _km_for_fip(db: Session, fip: Fip) -> KnowledgeModel | None:
    return db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))


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


def _questions_by_id(km: KnowledgeModel) -> dict[str, dict[str, Any]]:
    content = km.content or {}
    return {
        question["id"]: question
        for section in content.get("sections", [])
        for question in section.get("questions", [])
    }


def _validate_question_ids(answers: list[Answer], km: KnowledgeModel) -> None:
    """400 `unknown_question_id` for an answer whose question id the model
    doesn't have; spec 08-workshop-picklists.md §1.1/§5.4: 422
    `free_text_not_allowed` for a `ferFreeText` declaration on a question
    with `allowFreeText: false`."""
    questions = _questions_by_id(km)
    if any(a.question_id not in questions for a in answers):
        raise HTTPException(status_code=400, detail="unknown_question_id")
    for a in answers:
        if questions[a.question_id].get("allowFreeText") is False and any(
            d.fer_free_text for d in a.declarations
        ):
            raise HTTPException(status_code=422, detail="free_text_not_allowed")


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
        # spec 08-workshop-picklists.md §3.2: a multi-ref session offers
        # several questionnaires (one per area); the body ref must match
        # *one of* the session's refs (was: must equal the session's single
        # ref) -- the chosen ref becomes the FIP's questionnaire_id/version,
        # no new FIP column.
        allowed_refs = {
            (ref["id"], ref["version"]) for ref in session_questionnaire_refs(session_row)
        }
        if (body.questionnaire_ref.id, body.questionnaire_ref.version) not in allowed_refs:
            raise HTTPException(status_code=400, detail="questionnaire_ref_mismatch")
        questionnaire_id = body.questionnaire_ref.id
        questionnaire_version = body.questionnaire_ref.version
    else:
        questionnaire_id = body.questionnaire_ref.id
        questionnaire_version = body.questionnaire_ref.version

    km = get_readable_published_km(db, questionnaire_id, questionnaire_version, user)
    _validate_question_ids(body.answers, km)

    answers = [answer_dump(a) for a in body.answers]
    community = body.community.model_dump(mode="json", by_alias=True) if body.community else None
    related_dmps = normalise_related_dmps(
        [d.model_dump(mode="json", by_alias=True) for d in body.related_dmps], settings
    )
    apply_dmp_evidence(answers, related_dmps)
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
        return _out_for_km(fip, km, db, edit_token=edit_token)

    if user is not None:
        visibility = body.visibility or "private"
        check_email_verification_gate(user, visibility)
        fip = _insert_fip(
            db,
            settings,
            owner_id=user.id,
            session_id=None,
            edit_token_hash=None,
            visibility=visibility,
            **common,
        )
        return _out_for_km(fip, km, db)

    raise HTTPException(status_code=400, detail="session_id_or_login_required")


@router.post("/import", status_code=201)
def import_fip(
    body: FipImportDoc, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> dict[str, Any]:
    settings = get_settings()
    # spec 07-mail-and-migration.md §6: `exportVersion` 1 or 2 both import;
    # anything else is a document this backend doesn't understand.
    if body.export_version not in (1, 2):
        raise HTTPException(status_code=400, detail="unsupported_export_version")
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
    # Audit finding 3: importing straight into visibility="public" must
    # respect the same email-verification gate every other write to
    # visibility does.
    check_email_verification_gate(user, visibility)

    related_dmps = normalise_related_dmps(fip_data.get("relatedDMPs") or [], settings)

    try:
        reconstructed = reconstruct_answers_from_export(body.answers, language, related_dmps)
        answers = [Answer.model_validate(a) for a in reconstructed]
    except (KeyError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="invalid_answers") from exc

    _validate_question_ids(answers, km)
    community = fip_data.get("community")

    answer_dicts = [answer_dump(a) for a in answers]
    apply_dmp_evidence(answer_dicts, related_dmps)

    # spec 07 §6: `orphanedAnswers` is absent on a v1 document (empty list
    # default) and preserved verbatim -- declarations reconstructed the same
    # way as `answers` -- on a v2 one. Not re-validated against `km`'s
    # question ids: an orphaned answer's questionId is, by definition, one
    # the *current* questionnaire version may no longer have. The entry
    # *shape* is still validated (audit findings 4/11): a malformed
    # `orphanedAnswers` entry is 400 `invalid_orphaned_answers`, not an
    # unvalidated blob that can 500 later (e.g. RDF export).
    try:
        reconstructed_orphaned = reconstruct_orphaned_answers_from_export(
            body.orphaned_answers, language, related_dmps
        )
        orphaned_answers = [
            OrphanedAnswerImport.model_validate(o).model_dump(mode="json", by_alias=True)
            for o in reconstructed_orphaned
        ]
    except (KeyError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="invalid_orphaned_answers") from exc
    apply_dmp_evidence(orphaned_answers, related_dmps)

    # Audit finding 4: `migratedFrom` was taken verbatim from the request
    # body with no shape check -- validate it against the shape the
    # backend's own migrate endpoint writes.
    migrated_from_raw = fip_data.get("migratedFrom")
    migrated_from: dict[str, Any] | None = None
    if migrated_from_raw is not None:
        try:
            migrated_from = MigratedFromImport.model_validate(migrated_from_raw).model_dump(
                mode="json", by_alias=True
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="invalid_migrated_from") from exc

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
        related_dmps=related_dmps,
        answers=answer_dicts,
        orphaned_answers=orphaned_answers,
        migrated_from=migrated_from,
        language=language,
        license=fip_data.get("license") or "CC0-1.0",
    )
    return _out_for_km(fip, km, db)


@router.get("/{fip_id}")
def get_fip(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    fip = _get_readable_fip(fip_id, request, db, user)
    km = _km_for_fip(db, fip)
    return _out_for_km(fip, km, db)


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
    settings = get_settings()

    if body.visibility is not None:
        check_email_verification_gate(user, body.visibility)

    if body.community is not None:
        community = body.community.model_dump(mode="json", by_alias=True)
        fip.community = community
        fip.title = community.get("name")

    km = _km_for_fip(db, fip)
    if body.answers is not None:
        if km is not None:
            _validate_question_ids(body.answers, km)
        new_answers = [answer_dump(a) for a in body.answers]
    else:
        # A copy, not the ORM-tracked list itself: mutated in place below
        # only by the legacy-dmpEvidence normalisation pass, never
        # re-validated (review finding 1).
        new_answers = copy.deepcopy(fip.answers or [])

    if body.related_dmps is not None:
        new_related_dmps = normalise_related_dmps(
            [d.model_dump(mode="json", by_alias=True) for d in body.related_dmps], settings
        )
    else:
        new_related_dmps = fip.related_dmps or []

    # Review finding 1: silently migrate any legacy `{url, questionRef}`
    # dmpEvidence to the current `{dmpIndex, ...}` shape whenever a PATCH
    # gives us the chance to look at it, regardless of what the request
    # body touched -- this alone never rejects the PATCH.
    normalise_legacy_dmp_evidence(new_answers, new_related_dmps)

    if body.answers is not None:
        # spec 06-dmp-linkage.md §2.2: only the evidence in *this request's*
        # answers is validated against the FIP's final relatedDMPs. A PATCH
        # that omits `answers` never re-validates the FIP's already-stored
        # evidence (review finding 1): a legacy-shaped or now-out-of-range
        # dmpIndex left over from before this was normalised/tightened
        # would otherwise wedge every future PATCH (e.g. one that only
        # changes `visibility`) shut with a permanent 422. Evidence that
        # can no longer be resolved is instead handled gracefully at
        # read/export time (`resolve_dmp_evidence_for_export`).
        apply_dmp_evidence(new_answers, new_related_dmps)

    # Persisted unconditionally: even a PATCH that didn't touch `answers`
    # may have had legacy dmpEvidence migrated by the normalisation pass
    # above (a no-op copy otherwise).
    fip.answers = new_answers
    if body.related_dmps is not None:
        fip.related_dmps = new_related_dmps
    if body.language is not None:
        fip.language = body.language
    if body.license is not None:
        fip.license = body.license
    if body.visibility is not None:
        fip.visibility = body.visibility

    db.commit()
    db.refresh(fip)
    return _out_for_km(fip, km, db)


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
    km = _km_for_fip(db, fip)
    return _out_for_km(fip, km, db)


# ---------------------------------------------------------------------------
# Migration between knowledge-model versions (spec 07-mail-and-migration.md §4)
# ---------------------------------------------------------------------------


def _get_fip_for_migration(fip_id: str, request: Request, db: Session, user: User | None) -> Fip:
    """spec §4.3: "Authorization is exactly PATCH /api/fips/{id}" for all
    three migration endpoints -- unreadable -> 404, readable but not
    writable -> 403, via the same `_authorize_fip_write` PATCH/DELETE use."""
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    _authorize_fip_write(fip, user, request, db)
    return fip


def _migration_target_rows(db: Session, fip: Fip, user: User | None) -> list[KnowledgeModel]:
    """Published, readable, semver-greater versions of the FIP's own model
    id, ascending (spec §4.3). Same id only in v2 (spec §4)."""
    rows = (
        db.query(KnowledgeModel)
        .filter(
            KnowledgeModel.id == fip.questionnaire_id,
            KnowledgeModel.status == "published",
        )
        .all()
    )
    current_key = semver_key(fip.questionnaire_version)
    candidates = [
        row
        for row in rows
        if can_read(row.owner_id, row.visibility, user) and semver_key(row.version) > current_key
    ]
    candidates.sort(key=lambda row: semver_key(row.version))
    return candidates


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def _get_migration_target_km(
    db: Session, fip: Fip, to_version: str, user: User | None
) -> KnowledgeModel:
    """404 `target_not_found` unless `to_version` names a published, readable
    version of the FIP's own model id (spec §4.3)."""
    target = db.get(KnowledgeModel, (fip.questionnaire_id, to_version))
    if (
        target is None
        or target.status != "published"
        or not can_read(target.owner_id, target.visibility, user)
    ):
        raise HTTPException(status_code=404, detail="target_not_found")
    return target


def _compute_migration_diff(db: Session, fip: Fip, target: KnowledgeModel) -> dict[str, Any]:
    current_km = _km_for_fip(db, fip)
    current_content = current_km.content if current_km is not None else {}
    return compute_diff(
        {"id": fip.questionnaire_id, "version": fip.questionnaire_version},
        {
            "id": target.id,
            "version": target.version,
            "changelog": changelog_between(
                target.changelog or [], fip.questionnaire_version, target.version
            ),
        },
        current_content,
        target.content or {},
        fip.answers or [],
    )


@router.get("/{fip_id}/migration-targets")
def get_migration_targets(
    fip_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    fip = _get_fip_for_migration(fip_id, request, db, user)
    targets = _migration_target_rows(db, fip, user)
    items = [
        {
            "id": row.id,
            "version": row.version,
            "title": row.title,
            "changelog": changelog_between(
                row.changelog or [], fip.questionnaire_version, row.version
            ),
            # No separate `published_at` column exists (spec 04's
            # KnowledgeModel row has no such field): `updated_at` at publish
            # time is the closest available proxy and is what this returns.
            "publishedAt": _iso_utc(row.updated_at),
        }
        for row in targets
    ]
    return {
        "current": {"id": fip.questionnaire_id, "version": fip.questionnaire_version},
        "items": items,
        "total": len(items),
    }


@router.get("/{fip_id}/migration-preview")
def get_migration_preview(
    fip_id: str,
    request: Request,
    to: str = Query(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    fip = _get_fip_for_migration(fip_id, request, db, user)
    target = _get_migration_target_km(db, fip, to, user)
    if not semver_gt(to, fip.questionnaire_version):
        raise HTTPException(status_code=400, detail="version_not_greater")
    return _compute_migration_diff(db, fip, target)


@router.post("/{fip_id}/migrate")
def migrate_fip(
    fip_id: str,
    body: MigrateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    fip = _get_fip_for_migration(fip_id, request, db, user)

    # spec §4: session FIPs are pinned to their session's questionnaire_version.
    if fip.session_id is not None:
        session_row = db.get(WorkshopSession, fip.session_id)
        if session_row is not None and body.to != session_row.questionnaire_version:
            raise HTTPException(status_code=409, detail="session_version_pinned")

    target = _get_migration_target_km(db, fip, body.to, user)
    if body.to == fip.questionnaire_version:
        raise HTTPException(status_code=409, detail="already_on_version")
    if not semver_gt(body.to, fip.questionnaire_version):
        raise HTTPException(status_code=400, detail="version_not_greater")

    diff = _compute_migration_diff(db, fip, target)
    decisions = body.decisions.model_dump(mode="json", by_alias=True) if body.decisions else None
    try:
        new_answers, orphaned = apply_migration(
            diff, fip.answers or [], decisions, fip.questionnaire_version
        )
    except MigrationError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc

    now = datetime.now(UTC)
    fip.migrated_from = {
        "id": fip.questionnaire_id,
        "version": fip.questionnaire_version,
        "at": _iso_utc(now),
    }
    fip.questionnaire_id = target.id
    fip.questionnaire_version = target.version
    fip.answers = new_answers
    fip.orphaned_answers = [*(fip.orphaned_answers or []), *orphaned]
    fip.updated_at = now
    db.commit()
    db.refresh(fip)
    return _out_for_km(fip, target, db)


@router.post("/{fip_id}/prefill-from-dmp")
def prefill_from_dmp(
    fip_id: str,
    body: PrefillFromDmpRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    """spec 06-dmp-linkage.md §4: stub -- the URL is validated (bad URL ->
    422 dmp_url_invalid), auth is the FIP write rule, and the handler always
    returns 501 with a body describing what a real implementation needs.
    No frontend calls this in v2.0; the ICTIC demo calls it from /docs."""
    fip = db.get(Fip, fip_id)
    if fip is None:
        raise HTTPException(status_code=404, detail="not_found")
    _authorize_fip_write(fip, user, request, db)

    normalised = normalise_related_dmps([{"url": body.dmp_url}])
    entry = normalised[0]
    return JSONResponse(
        status_code=501,
        content={
            "detail": "fiodmp_api_unavailable",
            "dmpUrl": entry["url"],
            "system": entry["system"],
            "requires": {
                "endpoint": "GET /api/plans/{id}",
                "format": "RDA DMP Common Standard (maDMP) 1.1 JSON",
                "reference": "https://github.com/RDA-DMP-Common/RDA-DMP-Common-Standard",
                "contract": "docs/integration/fiodmp-api-contract.md",
            },
            "message": (
                "FioDMP exposes no machine-readable plan export yet; the "
                "FIP→DMP link works by URL today."
            ),
        },
    )


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
    comments = orphaned_answer_comment_lines(fip)
    return Response(
        content=to_turtle(g, comments),
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
