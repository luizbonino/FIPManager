"""SQLAlchemy 2.x declarative models. See docs/specs/01-foundations.md §2."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    # v4 (spec 05-v1-completion.md §1): set True by POST /admin/users/{id}/
    # reset-password, cleared by POST /auth/password on success. Enforced by
    # fipm.auth.password_change_middleware, not a per-route dependency (see
    # its docstring for why).
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # v4 (spec 05-v1-completion.md §2): the data/i18n/privacy/*.md version the
    # user accepted at registration; None for accounts created before this
    # change existed.
    privacy_accepted_version: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("ix_users_email", "email", unique=True),)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )


class KnowledgeModel(Base):
    __tablename__ = "knowledge_models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="public")
    status: Mapped[str] = mapped_column(String, nullable=False, default="published")
    license: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    # Review finding 12: `isSystem` (KnowledgeModelSummary) must be true only
    # for the rows the importer loads from data/knowledge-models/*.json, not
    # merely `owner_id IS NULL` -- account deletion (routers/auth.py) also
    # sets owner_id=NULL on an anonymised ex-user's published models, which
    # are community content, not built-in system models.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[dict] = mapped_column(JSON, nullable=False)
    changelog: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        Index("ix_km_owner_status", "owner_id", "status"),
        Index("ix_km_status_visibility", "status", "visibility"),
    )


class Fip(Base):
    __tablename__ = "fips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("workshop_sessions.id"), nullable=True
    )
    edit_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="private")
    questionnaire_id: Mapped[str] = mapped_column(String, nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    community: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    related_dmps: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    answers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    language: Mapped[str] = mapped_column(String, nullable=False)
    license: Mapped[str] = mapped_column(String, nullable=False, default="CC0-1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["questionnaire_id", "questionnaire_version"],
            ["knowledge_models.id", "knowledge_models.version"],
        ),
        Index("ix_fips_owner_updated", "owner_id", "updated_at"),
        Index("ix_fips_session_created", "session_id", "created_at"),
    )


class Fer(Base):
    __tablename__ = "fers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[dict] = mapped_column(JSON, nullable=False)
    label_search: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    homepage: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False, default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_fers_type_label_search", "type", "label_search"),
        Index("ix_fers_owner_id", "owner_id"),
    )


class WorkshopSession(Base):
    __tablename__ = "workshop_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    join_code: Mapped[str] = mapped_column(String(6), nullable=False)
    # Nullable (not NOT NULL as originally spec'd): an account deletion closes
    # and anonymises the facilitator's sessions rather than blocking on FK.
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    questionnaire_id: Mapped[str] = mapped_column(String, nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(String, nullable=False)
    default_language: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        Index("ix_sessions_join_code", "join_code", unique=True),
        Index("ix_sessions_owner_created", "owner_id", "created_at"),
    )


class Feedback(Base):
    """v4 (spec 05-v1-completion.md §4): anonymous by construction -- no
    user_id, no IP, no edit token stored. `session_id`/`fip_id` are set NULL
    (not cascaded) when the referenced row is deleted, so previously
    collected feedback stays readable via the GET routes."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("workshop_sessions.id", ondelete="SET NULL"), nullable=True
    )
    fip_id: Mapped[str | None] = mapped_column(
        ForeignKey("fips.id", ondelete="SET NULL"), nullable=True
    )
    q1: Mapped[int] = mapped_column(Integer, nullable=False)
    q2: Mapped[int] = mapped_column(Integer, nullable=False)
    q3: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_feedback_session_id", "session_id"),)


class SchemaVersionRow(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
