"""Pydantic v2 request/response models. Bodies are camelCase on the wire."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from fipm.config import DECLARATION_STATUSES


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# Visibility and session-status values (spec 01-foundations.md §2/§5/§6). Plain
# `Literal`s, not DB-native enums: the columns stay `String` per the spec.
Visibility = Literal["private", "link", "public"]
SessionStatus = Literal["open", "closed"]
# spec 02-core-flows.md §5.5: the three languages the frontend ships UI
# strings for. Plain `Literal`, not a DB-native enum (columns stay `String`).
Language = Literal["en", "pt-PT", "pt-BR"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthOut(CamelModel):
    status: str
    version: str
    schema_version: int
    time: datetime


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


class RegisterRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str
    language: str | None = None


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(CamelModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class DeleteAccountRequest(CamelModel):
    current_password: str


class UserOut(CamelModel):
    id: str
    email: str
    display_name: str
    role: str
    language: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Knowledge models
# ---------------------------------------------------------------------------


class QuestionnaireRef(CamelModel):
    id: str
    version: str


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
    url: str | None = None
    question_ref: str | None = None


class Declaration(CamelModel):
    fer_id: str | None = None
    fer_free_text: str | None = None
    status: str
    note: dict[str, str] | None = None
    dmp_evidence: DmpEvidence | None = None

    @model_validator(mode="after")
    def _fer_xor(self) -> Declaration:
        has_id = bool(self.fer_id)
        has_text = bool(self.fer_free_text)
        if has_id == has_text:
            raise ValueError("exactly one of ferId or ferFreeText must be set")
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


class FipImportDoc(CamelModel):
    """Body of POST /api/fips/import: the §3.1 export document, verbatim."""

    export_version: int
    generated_at: datetime | None = None
    tool: dict[str, Any] | None = None
    fip: dict[str, Any]
    questionnaire_ref: QuestionnaireRef
    answers: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionCreateRequest(CamelModel):
    title: str
    questionnaire_ref: QuestionnaireRef
    default_language: Language


class SessionPatchRequest(CamelModel):
    title: str | None = None
    status: SessionStatus | None = None
    default_language: Language | None = None


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


# ---------------------------------------------------------------------------
# ORM -> schema converters for shapes that don't map 1:1 onto a model
# (Fip has no plaintext edit_token column; WorkshopSession has no join_url).
# ---------------------------------------------------------------------------


def fip_to_out(fip: Any, edit_token: str | None = None) -> FipOut:
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
        answers=fip.answers or [],
        language=fip.language,
        license=fip.license,
        created_at=fip.created_at,
        updated_at=fip.updated_at,
        edit_token=edit_token,
    )


def fip_out_dict(fip: Any, edit_token: str | None = None) -> dict[str, Any]:
    """FipOut as a camelCase dict, with the editToken key entirely absent
    (never merely null) unless it was actually issued."""
    data = fip_to_out(fip, edit_token).model_dump(mode="json", by_alias=True)
    if data.get("editToken") is None:
        data.pop("editToken", None)
    return data


def km_summary_dict(row: Any) -> dict[str, Any]:
    """KnowledgeModelSummary as a camelCase dict, with `questionCount` (non-
    hidden questions) and `forkedFrom` read out of the row's `content` JSON
    (spec 04-knowledge-model-editor.md §3 API #1)."""
    content = row.content or {}
    question_count = sum(
        1
        for section in (content.get("sections") or [])
        for question in (section.get("questions") or [])
        if question.get("hidden") is not True
    )
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
        is_system=row.owner_id is None,
        question_count=question_count,
        forked_from=content.get("forkedFrom"),
    )
    return summary.model_dump(mode="json", by_alias=True)


def session_to_out(row: Any, base_url: str) -> SessionOut:
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
    )
