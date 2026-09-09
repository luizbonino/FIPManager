"""Pydantic v2 request/response models. Bodies are camelCase on the wire."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from fipm.config import DECLARATION_STATUSES, Settings, get_settings


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# Visibility and session-status values (spec 01-foundations.md §2/§5/§6). Plain
# `Literal`s, not DB-native enums: the columns stay `String` per the spec.
Visibility = Literal["private", "link", "public"]
SessionStatus = Literal["open", "closed"]
# spec 02-core-flows.md §5.5: the four languages the frontend ships UI
# strings for. Plain `Literal`, not a DB-native enum (columns stay `String`).
Language = Literal["en", "pt-PT", "pt-BR", "es"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthOut(CamelModel):
    status: str
    version: str
    schema_version: int
    time: datetime
    # spec 05-v1-completion.md §2/§4: additive, so the pre-v1-completion
    # frontend (which only reads status/version/schemaVersion/time) keeps
    # working unchanged.
    contact_email: str = ""
    hosting_org: str = ""
    feedback_enabled: bool = True
    privacy_version: str | None = None
    languages: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


class RegisterRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str
    language: str | None = None
    # spec 05-v1-completion.md §2: required, non-empty -- an absent value is
    # pydantic's own 422; a value that doesn't match the current privacy
    # notice version is a router-level 400 privacy_version_mismatch.
    privacy_accepted_version: str = Field(min_length=1)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(CamelModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class DeleteAccountRequest(CamelModel):
    current_password: str


# ---------------------------------------------------------------------------
# Mail-backed account flows (spec 07-mail-and-migration.md §2/§3)
# ---------------------------------------------------------------------------


class VerifyEmailRequest(CamelModel):
    token: str


class PasswordResetRequestRequest(CamelModel):
    email: str


class PasswordResetConfirmRequest(CamelModel):
    token: str
    # spec §3: reuses RegisterRequest's 10-128 char validator.
    new_password: str = Field(min_length=10, max_length=128)


class UserOut(CamelModel):
    id: str
    email: str
    display_name: str
    role: str
    language: str
    created_at: datetime
    updated_at: datetime
    must_change_password: bool = False
    privacy_accepted_version: str | None = None
    # spec 07-mail-and-migration.md §2: null until POST /api/auth/verify-email
    # (or a password-reset confirm, which also proves control of the mailbox)
    # succeeds.
    email_verified_at: datetime | None = None


# ---------------------------------------------------------------------------
# Knowledge models
# ---------------------------------------------------------------------------


class QuestionnaireRef(CamelModel):
    id: str
    version: str


# spec 08-workshop-picklists.md §3.1: one entry of a session's
# `questionnaireRefs`, as accepted on write -- `label` is facilitator-
# authored (no `en` requirement, capped at 80 chars/language by
# `km_content.validate_langmap`, checked in the router alongside id/version
# resolution).
class QuestionnaireRefLabelled(CamelModel):
    id: str
    version: str
    label: dict[str, str] = Field(default_factory=dict)


# spec 08 §3.1: one entry of a session's `questionnaireRefs` as returned on
# read -- `title` is the model's own title, filtered by the same
# anonymous-readability rule that guards `questionnaireTitle` today.
class QuestionnaireRefOut(CamelModel):
    id: str
    version: str
    label: dict[str, str]
    title: dict[str, str]


class KnowledgeModelSummary(CamelModel):
    id: str
    version: str
    status: str
    visibility: str
    license: str
    title: dict[str, str]
    description: dict[str, str]
    created_at: datetime
    updated_at: datetime
    # spec 04-knowledge-model-editor.md §3 API #1: additive fields, existing
    # ones kept so the pre-week-3 frontend keeps working.
    owner_id: str | None = None
    is_system: bool = False
    # True only for a shipped `status: "draft"` model (is_system=False,
    # owner_id=None) awaiting facilitator review/claim -- lets the frontend
    # group these separately from a published system model or a user's own
    # draft (routers.knowledge_models.list_knowledge_models, importer.py).
    is_unowned_draft: bool = False
    question_count: int = 0
    forked_from: dict[str, str] | None = None


class KnowledgeModelVersionEntry(CamelModel):
    version: str
    status: str
    changelog: list[dict[str, Any]]


class KnowledgeModelOut(CamelModel):
    id: str
    version: str
    status: str
    visibility: str
    license: str
    source: str
    title: dict[str, str]
    description: dict[str, str]
    changelog: list[dict[str, Any]]
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    owner_id: str | None = None


class ListOut(CamelModel):
    items: list[Any]
    total: int


# ---------------------------------------------------------------------------
# Knowledge models -- write requests (spec 04-knowledge-model-editor.md §3)
# ---------------------------------------------------------------------------


class KnowledgeModelCreateRequest(CamelModel):
    id: str | None = None
    title: dict[str, str]
    description: dict[str, str] | None = None
    license: str | None = None
    sections: list[dict[str, Any]] | None = None


class KnowledgeModelForkRequest(CamelModel):
    new_id: str | None = None
    title: dict[str, str] | None = None


class KnowledgeModelImportRequest(CamelModel):
    id: str | None = None
    document: dict[str, Any]


class KnowledgeModelPatchRequest(CamelModel):
    title: dict[str, str] | None = None
    description: dict[str, str] | None = None
    visibility: Visibility | None = None


class KnowledgeModelContentPutRequest(CamelModel):
    sections: list[dict[str, Any]]
    title: dict[str, str] | None = None
    description: dict[str, str] | None = None
    # spec 08-workshop-picklists.md §1.1/§1.4: siblings of `sections`, edited
    # through this same whole-document PUT (no new endpoint). `None` means
    # "leave this field as it is on the row" (an editor session that never
    # touched the settings panel must not silently clear it); an explicit
    # `[]`/`false`/status string does update it, including "unset" writes
    # coming from the editor UI.
    inline_fers: list[dict[str, Any]] | None = None
    default_declaration_status: str | None = None
    compact_declarations: bool | None = None


class KnowledgeModelPublishRequest(CamelModel):
    # Deliberately unconstrained (no min_length): an absent `notes` key is a
    # 422 (AC2), an empty string is a 400 `changelog_notes_required` handled
    # in the router -- pydantic must accept "" for that distinction to work.
    notes: str = Field(max_length=2000)


class KnowledgeModelNewVersionRequest(CamelModel):
    bump: Literal["minor", "patch", "major"] | None = None
    version: str | None = None


# ---------------------------------------------------------------------------
# FERs
# ---------------------------------------------------------------------------


class FerCreateRequest(CamelModel):
    id: str
    label: dict[str, str]
    type: str
    homepage: str | None = None


class FerOut(CamelModel):
    id: str
    label: dict[str, str]
    type: str
    homepage: str | None
    source: str


# ---------------------------------------------------------------------------
# FIP answers
# ---------------------------------------------------------------------------


class DmpEvidence(CamelModel):
    """spec 06-dmp-linkage.md §2.1: `{dmpIndex, section, questionRef}`.
    Fields are deliberately untyped (`Any`) rather than `int | None` etc.:
    validation (missing/wrong-type/out-of-range `dmpIndex`, oversized
    `section`/`questionRef`) lives in `fipm.dmp.apply_dmp_evidence`, not
    here, so failures keep the API-wide `{"detail": "<code>"}` shape
    instead of Pydantic's error array. Writers only ever produce this
    shape; the legacy `{url, questionRef}` shape some stored data may still
    carry is read directly out of the JSON column by exporters/rdf/import,
    never through this model."""

    dmp_index: Any = None
    section: Any = None
    question_ref: Any = None


# Review finding 8: ferId/successorFerId are meant to be FER identifiers --
# IRIs, either http(s) URLs (the common case: FERs are typically resolvable
# registry/service homepages) or urn: URNs -- not arbitrary free text
# (that's what ferFreeText/successorFreeText are for). No control characters
# or whitespace anywhere in the value; \S already excludes whitespace, so
# only C0/DEL control characters need a separate check.
_FER_IRI_RE = re.compile(r"^(?:https?://|urn:)\S+$")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _validate_fer_iri(value: str) -> str:
    if _CONTROL_CHAR_RE.search(value) or not _FER_IRI_RE.match(value):
        raise ValueError(
            "must be an http(s):// or urn: IRI with no whitespace/control characters "
            "(invalid_fer_iri)"
        )
    return value


class Declaration(CamelModel):
    fer_id: str | None = None
    fer_free_text: str | None = None
    status: str
    note: dict[str, str] | None = None
    dmp_evidence: DmpEvidence | None = None
    # spec 05-v1-completion.md §5 (closes spec 03 §6): the resource that will
    # replace this one, only meaningful (and only allowed) when
    # status == "planned-replacement". No DB change -- lives in the `answers`
    # JSON like every other declaration field.
    successor_fer_id: str | None = None
    successor_free_text: str | None = None

    @field_validator("fer_id", "successor_fer_id")
    @classmethod
    def _fer_id_fields_are_iris(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_fer_iri(v)

    @model_validator(mode="after")
    def _fer_xor(self) -> Declaration:
        has_id = bool(self.fer_id)
        has_text = bool(self.fer_free_text)
        if has_id == has_text:
            raise ValueError("exactly one of ferId or ferFreeText must be set")
        return self

    @model_validator(mode="after")
    def _successor_rules(self) -> Declaration:
        has_id = bool(self.successor_fer_id)
        has_text = bool(self.successor_free_text)
        if has_id and has_text:
            raise ValueError("at most one of successorFerId or successorFreeText may be set")
        if (has_id or has_text) and self.status != "planned-replacement":
            raise ValueError(
                "successorFerId/successorFreeText require status == 'planned-replacement'"
            )
        # Review finding 8: a "replacement" that points right back at
        # itself isn't a replacement.
        if has_id and self.successor_fer_id == self.fer_id:
            raise ValueError("successorFerId must not equal ferId (successor_same_as_fer)")
        return self

    @field_validator("status")
    @classmethod
    def _status_allowed(cls, v: str) -> str:
        if v not in DECLARATION_STATUSES:
            raise ValueError(f"status must be one of {DECLARATION_STATUSES}")
        return v


class Answer(CamelModel):
    question_id: str
    declarations: list[Declaration] = Field(default_factory=list)
    comment: str | None = None
    # spec 08-workshop-picklists.md §2.1: a per-answer "not applicable" flag,
    # mutually exclusive with declarations -- 422 on both
    # `POST /api/fips`, `PATCH /api/fips/{id}` and `POST /api/fips/import`.
    not_applicable: bool = False

    @model_validator(mode="after")
    def _not_applicable_excludes_declarations(self) -> Answer:
        if self.not_applicable and self.declarations:
            raise ValueError(
                "notApplicable and declarations are mutually exclusive "
                "(not_applicable_with_declarations)"
            )
        return self


def answer_dump(answer: Answer) -> dict[str, Any]:
    """`Answer` -> the stored/exported dict shape, with `notApplicable`
    entirely absent (never merely `false`) unless it's actually `true` --
    spec 08 §2.1: "notApplicable: false is never stored ... keeping old
    `answers` blobs byte-identical"."""
    data = answer.model_dump(mode="json", by_alias=True)
    if data.get("notApplicable") is False:
        data.pop("notApplicable", None)
    return data


class MigratedFromImport(CamelModel):
    """Audit finding 4: `POST /fips/import`'s `fip.migratedFrom` (spec 07
    §4.4) used to be taken verbatim from the request body with no shape
    check at all. The backend's own migrate endpoint only ever writes
    `{"id": ..., "version": ..., "at": ...}` (routers/fips.py's `migrate`),
    so that's the shape enforced here; a mismatch is 400
    `invalid_migrated_from` rather than an unvalidated blob reaching RDF
    export or a later migration."""

    id: str
    version: str
    at: str


class OrphanedAnswerImport(CamelModel):
    """Audit findings 4/11: one `fip.orphanedAnswers` entry on an imported
    export document (spec 07 §4.4/§6) -- an `Answer`-shaped
    `questionId`/`declarations`/`comment` plus the migration-provenance
    fields `questionText`/`fromVersion`/`at`. Before this, a malformed
    entry (e.g. a bad `declarations` shape) reached
    `rdf.orphaned_answer_comment_lines` / RDF export unvalidated and could
    500 instead of failing the import with 400 `invalid_orphaned_answers`."""

    question_id: str
    question_text: dict[str, str] = Field(default_factory=dict)
    declarations: list[Declaration] = Field(default_factory=list)
    comment: str | None = None
    # spec 08-workshop-picklists.md §2.3: an orphaned answer carries its
    # "not applicable" flag along, same as an active one.
    not_applicable: bool = False
    from_version: str | None = None
    at: str | None = None


class DataSteward(CamelModel):
    orcid: str | None = None
    name: str | None = None


class Community(CamelModel):
    name: str | None = None
    description: str | None = None
    links: list[str] = Field(default_factory=list)
    domain: str | None = None
    data_steward: DataSteward | None = None


class RelatedDmp(CamelModel):
    url: str
    version: str | None = None
    system: str | None = None
    # spec 06-dmp-linkage.md §1.1: derived server-side by
    # `fipm.dmp.normalise_related_dmps` and ignored on input (a client-sent
    # `system`/`dmpId` is overwritten) -- present here so a client that
    # echoes back a previously-normalised entry (e.g. a PATCH built from the
    # last GET) round-trips without an unknown-field surprise.
    dmp_id: str | None = None


# ---------------------------------------------------------------------------
# FIPs
# ---------------------------------------------------------------------------


class FipCreateRequest(CamelModel):
    questionnaire_ref: QuestionnaireRef
    language: Language | None = None
    community: Community | None = None
    answers: list[Answer] = Field(default_factory=list)
    visibility: Visibility | None = None
    session_id: str | None = None
    join_code: str | None = None
    related_dmps: list[RelatedDmp] = Field(default_factory=list)
    license: str | None = None


class FipPatchRequest(CamelModel):
    community: Community | None = None
    answers: list[Answer] | None = None
    related_dmps: list[RelatedDmp] | None = None
    language: Language | None = None
    license: str | None = None
    visibility: Visibility | None = None


class FipSummary(CamelModel):
    """spec 06-dmp-linkage.md §3.1: cheap per-FIP counts a consumer (e.g.
    FioDMP) can render without fetching the full `answers` array."""

    answered_questions: int
    total_questions: int | None
    declarations: int
    by_status: dict[str, int]
    # spec 08-workshop-picklists.md §2.2: count of answers flagged
    # `notApplicable: true` (a subset of `answeredQuestions`; `byStatus`
    # stays about declaration statuses only).
    not_applicable: int = 0


class FipOut(CamelModel):
    id: str
    owner_id: str | None
    session_id: str | None
    visibility: str
    questionnaire_id: str
    questionnaire_version: str
    title: str | None
    community: dict[str, Any] | None
    related_dmps: list[dict[str, Any]]
    answers: list[dict[str, Any]]
    language: str
    license: str
    created_at: datetime
    updated_at: datetime
    edit_token: str | None = None
    # spec 06-dmp-linkage.md §3.1: two cheap additions for FioDMP.
    embed_url: str
    summary: FipSummary
    # spec 07-mail-and-migration.md §0/§4.3: the version migrated *from* on
    # the last migration, or null.
    migrated_from: dict[str, Any] | None = None
    # spec 08-workshop-picklists.md §3.2: the label of the session ref this
    # FIP was created against, looked up from the session's ref list at
    # read/export time (never copied onto the FIP row) -- non-null only for
    # a FIP in a multi-ref session.
    area_label: dict[str, str] | None = None


class PrefillFromDmpRequest(CamelModel):
    """Body of POST /api/fips/{id}/prefill-from-dmp (spec 06 §4)."""

    dmp_url: str


class MigrateDecisions(CamelModel):
    """Body of `POST /api/fips/{id}/migrate`'s `decisions` (spec 07 §4.3):
    `{oldQuestionId -> chosen target ids}` for a `split` item, `{oldQuestionId
    -> chosen target id}` for a `removed` item. Untyped inner values aren't
    needed here -- `fipm.migration.apply_migration` validates every key/value
    against the recomputed diff and raises `unknown_decision`/
    `invalid_decision`, not pydantic."""

    split_copies: dict[str, list[str]] | None = None
    orphan_reassign: dict[str, str] | None = None


class MigrateRequest(CamelModel):
    to: str
    decisions: MigrateDecisions | None = None


class FipImportDoc(CamelModel):
    """Body of POST /api/fips/import: the §3.1 export document, verbatim.
    spec 07-mail-and-migration.md §6: `exportVersion` 1 or 2 are both
    accepted; `orphanedAnswers` is absent on a v1 document (default `[]`)
    and preserved verbatim (declarations reconstructed like `answers`) on a
    v2 one. `fip.migratedFrom` lives inside the untyped `fip` dict already."""

    export_version: int
    generated_at: datetime | None = None
    tool: dict[str, Any] | None = None
    fip: dict[str, Any]
    questionnaire_ref: QuestionnaireRef
    answers: list[dict[str, Any]]
    orphaned_answers: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionCreateRequest(CamelModel):
    title: str
    # spec 08-workshop-picklists.md §3.1: `questionnaire_ref` stays
    # "required-ish" -- optional here so a client may send only
    # `questionnaireRefs` instead, but the model validator below rejects a
    # body that supplies neither (422).
    questionnaire_ref: QuestionnaireRef | None = None
    questionnaire_refs: list[QuestionnaireRefLabelled] | None = Field(
        default=None, min_length=1, max_length=12
    )
    default_language: Language

    @model_validator(mode="after")
    def _at_least_one_ref(self) -> SessionCreateRequest:
        if self.questionnaire_ref is None and not self.questionnaire_refs:
            raise ValueError("questionnaire_ref or questionnaire_refs is required")
        return self


class SessionPatchRequest(CamelModel):
    title: str | None = None
    status: SessionStatus | None = None
    default_language: Language | None = None
    # spec 08 §3.1/§5.7: replaceable only while the session has no FIPs
    # (checked in the router -- 409 `session_has_fips`).
    questionnaire_refs: list[QuestionnaireRefLabelled] | None = Field(
        default=None, min_length=1, max_length=12
    )


class SessionOut(CamelModel):
    id: str
    join_code: str
    join_url: str
    owner_id: str
    questionnaire_id: str
    questionnaire_version: str
    default_language: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    # spec 08 §3.1/§5.8: the session's full ref list, each with its own
    # label and (anonymously-readability-filtered) title.
    questionnaire_refs: list[QuestionnaireRefOut] = Field(default_factory=list)


class SessionPublicOut(CamelModel):
    id: str
    title: str
    status: str
    questionnaire_ref: QuestionnaireRef
    default_language: str
    facilitator_name: str
    # spec 02-core-flows.md §5.1: the knowledge model's own `title` LangMap,
    # so the join screen can render it without a ~60 kB knowledge-model fetch.
    questionnaire_title: dict[str, str]
    # spec 08 §3.1/§5.8: as SessionOut.questionnaireRefs.
    questionnaire_refs: list[QuestionnaireRefOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ORM -> schema converters for shapes that don't map 1:1 onto a model
# (Fip has no plaintext edit_token column; WorkshopSession has no join_url).
# ---------------------------------------------------------------------------


def _non_hidden_question_ids(content: dict[str, Any]) -> set[str]:
    """Non-hidden question ids in a knowledge model's `content` (shared by
    `_question_count`'s/`km_summary_dict`'s `questionCount`,
    `FipOut.summary.totalQuestions`, and the set `_fip_summary` filters
    `answeredQuestions`/`byStatus` by, review finding 5)."""
    return {
        question["id"]
        for section in (content.get("sections") or [])
        for question in (section.get("questions") or [])
        if question.get("hidden") is not True
    }


def _question_count(content: dict[str, Any]) -> int:
    return len(_non_hidden_question_ids(content))


def total_questions_for_km(km: Any | None) -> int | None:
    """spec 06-dmp-linkage.md §3.1: `null` when the FIP's knowledge model
    row is missing (e.g. deleted since); otherwise its non-hidden question
    count, matching the padding `exporters.build_export_json` applies."""
    if km is None:
        return None
    return _question_count(km.content or {})


def known_question_ids_for_km(km: Any | None) -> set[str] | None:
    """Review finding 5: the same non-hidden question ids `total_questions_
    for_km` counts, for `_fip_summary` to filter `answers` by -- `None`
    (no filtering) when the FIP's knowledge model row is missing, matching
    `total_questions_for_km`'s own `None` in that case."""
    if km is None:
        return None
    return _non_hidden_question_ids(km.content or {})


def _fip_summary(
    answers: list[dict[str, Any]],
    total_questions: int | None,
    known_question_ids: set[str] | None = None,
) -> FipSummary:
    """Review finding 5: when `known_question_ids` is given, only answers to
    those (non-hidden) questions count towards `answeredQuestions`/
    `declarations`/`byStatus`, so an answer left behind for a since-hidden
    question can't push `answeredQuestions` past `totalQuestions`. `None`
    (knowledge model row missing, e.g. deleted since) counts every answer,
    same as before this filter existed."""
    by_status: dict[str, int] = dict.fromkeys(DECLARATION_STATUSES, 0)
    answered_questions = 0
    declarations = 0
    not_applicable = 0
    for answer in answers:
        if known_question_ids is not None and answer.get("questionId") not in known_question_ids:
            continue
        decls = answer.get("declarations") or []
        is_not_applicable = bool(answer.get("notApplicable"))
        # spec 08-workshop-picklists.md §2.2: a notApplicable answer counts
        # as answered even though it carries no declarations.
        if decls or is_not_applicable:
            answered_questions += 1
        if is_not_applicable:
            not_applicable += 1
        for decl in decls:
            declarations += 1
            status = decl.get("status")
            if status in by_status:
                by_status[status] += 1
    return FipSummary(
        answered_questions=answered_questions,
        total_questions=total_questions,
        declarations=declarations,
        by_status=by_status,
        not_applicable=not_applicable,
    )


def fip_to_out(
    fip: Any,
    edit_token: str | None = None,
    *,
    settings: Settings | None = None,
    total_questions: int | None = None,
    known_question_ids: set[str] | None = None,
    area_label: dict[str, str] | None = None,
) -> FipOut:
    if settings is None:
        settings = get_settings()
    answers = fip.answers or []
    return FipOut(
        id=fip.id,
        owner_id=fip.owner_id,
        session_id=fip.session_id,
        visibility=fip.visibility,
        questionnaire_id=fip.questionnaire_id,
        questionnaire_version=fip.questionnaire_version,
        title=fip.title,
        community=fip.community,
        related_dmps=fip.related_dmps or [],
        answers=answers,
        language=fip.language,
        license=fip.license,
        created_at=fip.created_at,
        updated_at=fip.updated_at,
        edit_token=edit_token,
        embed_url=f"{settings.base_url}/fips/{fip.id}/embed",
        summary=_fip_summary(answers, total_questions, known_question_ids),
        migrated_from=fip.migrated_from,
        area_label=area_label,
    )


def fip_out_dict(
    fip: Any,
    edit_token: str | None = None,
    *,
    settings: Settings | None = None,
    total_questions: int | None = None,
    known_question_ids: set[str] | None = None,
    area_label: dict[str, str] | None = None,
) -> dict[str, Any]:
    """FipOut as a camelCase dict, with the editToken key entirely absent
    (never merely null) unless it was actually issued."""
    data = fip_to_out(
        fip,
        edit_token,
        settings=settings,
        total_questions=total_questions,
        known_question_ids=known_question_ids,
        area_label=area_label,
    ).model_dump(mode="json", by_alias=True)
    if data.get("editToken") is None:
        data.pop("editToken", None)
    return data


# ---------------------------------------------------------------------------
# Session questionnaire refs (spec 08-workshop-picklists.md §0/§3)
# ---------------------------------------------------------------------------


def session_questionnaire_refs(row: Any) -> list[dict[str, Any]]:
    """The session's effective ref list: `row.questionnaire_refs` verbatim
    when set, else a single-entry list derived from
    `questionnaire_id`/`questionnaire_version` (NULL on a pre-v6 row, or a
    row created via the single-ref path -- spec §0). Pure (no DB access);
    callers that need a `title`/resolved `label` look those up against the
    referenced `KnowledgeModel` rows themselves."""
    refs = row.questionnaire_refs
    if refs:
        return refs
    return [{"id": row.questionnaire_id, "version": row.questionnaire_version, "label": {}}]


def area_label_for_refs(
    refs: list[dict[str, Any]], questionnaire_id: str, questionnaire_version: str
) -> dict[str, str] | None:
    """spec 08 §3.2: `FipOut.areaLabel` -- non-null only when `refs` has
    more than one entry (a multi-ref session); the label of the ref
    matching `questionnaire_id`/`questionnaire_version`, else None."""
    if len(refs) <= 1:
        return None
    for ref in refs:
        if ref.get("id") == questionnaire_id and ref.get("version") == questionnaire_version:
            return ref.get("label") or {}
    return None


def km_summary_dict(row: Any) -> dict[str, Any]:
    """KnowledgeModelSummary as a camelCase dict, with `questionCount` (non-
    hidden questions) and `forkedFrom` read out of the row's `content` JSON
    (spec 04-knowledge-model-editor.md §3 API #1)."""
    content = row.content or {}
    question_count = _question_count(content)
    summary = KnowledgeModelSummary(
        id=row.id,
        version=row.version,
        status=row.status,
        visibility=row.visibility,
        license=row.license,
        title=row.title,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
        owner_id=row.owner_id,
        is_system=row.is_system,
        is_unowned_draft=row.owner_id is None and not row.is_system,
        question_count=question_count,
        forked_from=content.get("forkedFrom"),
    )
    return summary.model_dump(mode="json", by_alias=True)


# ---------------------------------------------------------------------------
# Admin (spec 05-v1-completion.md §1)
# ---------------------------------------------------------------------------


class AdminUserOut(CamelModel):
    id: str
    email: str
    display_name: str
    role: str
    language: str
    created_at: datetime
    must_change_password: bool
    privacy_accepted_version: str | None
    fip_count: int
    session_count: int
    knowledge_model_count: int


class AdminResetPasswordOut(CamelModel):
    temporary_password: str


class AdminFipStatsOut(CamelModel):
    """spec 09-standalone-fips.md retention runbook: aggregate FIP counts by
    kind (spec 09 §2's authorization table), so an admin can see how many
    ownerless FIPs exist before running `purge-standalone-fips`."""

    owned_fips: int
    standalone_fips: int
    session_fips: int


class AdminFerOut(CamelModel):
    id: str
    label: dict[str, str]
    type: str
    homepage: str | None
    source: str
    owner_email: str | None
    usage_count: int


class AdminFerMergeRequest(CamelModel):
    target_fer_id: str


class AdminFerMergeOut(CamelModel):
    repointed_declarations: int
    repointed_fips: int
    # Review finding 2: knowledge-model rows (any id/version) whose content
    # had a question's suggestedFerIds re-pointed away from the merged FER.
    repointed_knowledge_models: int = 0


# ---------------------------------------------------------------------------
# Privacy notice (spec 05-v1-completion.md §2)
# ---------------------------------------------------------------------------


class PrivacyOut(CamelModel):
    version: str
    date: str
    lang: str
    markdown: str


# ---------------------------------------------------------------------------
# Feedback (spec 05-v1-completion.md §4)
# ---------------------------------------------------------------------------


class FeedbackCreateRequest(CamelModel):
    q1: int = Field(ge=1, le=5)
    q2: int = Field(ge=1, le=5)
    q3: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    session_id: str | None = None
    fip_id: str | None = None
    language: str | None = None


class FeedbackQuestionStat(CamelModel):
    key: str
    mean: float | None
    counts: dict[str, int]


class FeedbackCommentOut(CamelModel):
    text: str
    created_at: datetime


class FeedbackSummaryOut(CamelModel):
    responses: int
    questions: list[FeedbackQuestionStat]
    comments: list[FeedbackCommentOut]


def session_to_out(
    row: Any, base_url: str, questionnaire_refs: list[dict[str, Any]] | None = None
) -> SessionOut:
    return SessionOut(
        id=row.id,
        join_code=row.join_code,
        join_url=f"{base_url}/join/{row.join_code}",
        owner_id=row.owner_id,
        questionnaire_id=row.questionnaire_id,
        questionnaire_version=row.questionnaire_version,
        default_language=row.default_language,
        title=row.title,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        questionnaire_refs=questionnaire_refs or [],
    )
