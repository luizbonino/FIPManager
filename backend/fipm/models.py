"""SQLAlchemy 2.x declarative models. See docs/specs/01-foundations.md §2."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
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
    # v5 (spec 07-mail-and-migration.md §0): set by a successful
    # POST /api/auth/verify-email or password-reset/confirm; cleared when the
    # account email changes.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
    # v5 (spec 07-mail-and-migration.md §0/§4.3): `{"id","version","at"}` --
    # the version migrated *from* on the last migration; None until a FIP is
    # migrated at least once.
    migrated_from: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # v5 (spec 07 §4.4): append-only list of answers orphaned by a migration
    # (§4.4 shape); never re-injected into `answers`.
    orphaned_answers: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    # v7 (spec 11-nanopub-network.md §4): set only for a FIP created via
    # POST /api/fips/from-network -- {"communityIri", "fipNanopubIri",
    # "indexIri", "fetchedAt"}. NULL for every FIP not created from the
    # network (the pre-v7 value, meaning exactly that).
    network_origin: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["questionnaire_id", "questionnaire_version"],
            ["knowledge_models.id", "knowledge_models.version"],
        ),
        Index("ix_fips_owner_updated", "owner_id", "updated_at"),
        Index("ix_fips_session_created", "session_id", "created_at"),
        # v8 (spec 13-fip-dashboard.md §2.2): covering indexes for dashboard
        # population resolution -- created on an already-existing `fips`
        # table by `db._ensure_indexes()` (create_all() never adds indexes to
        # a pre-existing table), not merely declared here. Wide on purpose:
        # SELECT f.id behind a narrow index still needs a heap lookup, and
        # the `fips` heap page carries the whole `answers` JSON blob -- the
        # single most expensive page in the database. Covering them keeps
        # population resolution off the heap entirely.
        Index(
            "ix_fips_pop_vis",
            "visibility",
            "updated_at",
            "id",
            "session_id",
            "owner_id",
            "questionnaire_id",
            "questionnaire_version",
        ),
        Index("ix_fips_pop_sess", "session_id", "updated_at", "id", "visibility", "owner_id"),
        Index(
            "ix_fips_pop_km",
            "questionnaire_id",
            "questionnaire_version",
            "updated_at",
            "id",
            "visibility",
            "owner_id",
            "session_id",
        ),
        Index("ix_fips_pop_own", "owner_id", "updated_at", "id", "visibility", "session_id"),
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
    # v6 (spec 08-workshop-picklists.md §0/§3): `[{"id","version","label":
    # {lang:str}}]`, 1..12 entries. NULL on a pre-v6 row (or one created
    # without `questionnaireRefs`) means "derive the single-entry list from
    # questionnaire_id/questionnaire_version" -- see
    # fipm.routers.sessions.effective_questionnaire_refs. questionnaire_id/
    # questionnaire_version always hold refs[0] and stay the FK.
    questionnaire_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
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


class EmailToken(Base):
    """v5 (spec 07-mail-and-migration.md §0): a verify_email or password_reset
    token. `id` is the sha256 hex of the plaintext token (the plaintext is
    never stored -- it lives only in the mail sent to the user). `email` is
    the address the token was issued for, so a since-changed account email
    invalidates any outstanding token of that purpose (spec §2)."""

    __tablename__ = "email_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_email_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_email_tokens_expires_at", "expires_at"),
    )


class SchemaVersionRow(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# v8 (spec 13-fip-dashboard.md §1): the derived, write-maintained projection
# of `Fip.answers` that every dashboard view reads -- never `json_extract`,
# never the JSON column itself, in a per-request hot path (§1.1, §1.9).
# `fipm.projection` is the only writer; `fipm.dashboard.*` is the only
# reader. Six tables land here (brief A, spec §10.1); `FipSignature`,
# `FipSignatureBand`, `LshHotBucket`, `NetworkFip` and `DashboardSnapshot`
# land in brief B (§10.2).
# ---------------------------------------------------------------------------


class FipFacets(Base):
    """One row per FIP (spec §1.2) -- the cheap-to-join, expensive-to-derive
    per-FIP summary a view needs alongside its `fip_cells`/`fip_declarations`
    aggregate. Carries no authorization-meaning column (D2): population
    resolution never reads this table, only the authoritative `fips` one."""

    __tablename__ = "fip_facets"

    fip_id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'local' | 'network'
    questionnaire_id: Mapped[str] = mapped_column(String, nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(String, nullable=False)
    area_key: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    answered_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    not_applicable_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    declaration_count: Mapped[int] = mapped_column(Integer, nullable=False)
    current_declarations: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    migrated_from_id: Mapped[str | None] = mapped_column(String, nullable=True)
    migrated_from_version: Mapped[str | None] = mapped_column(String, nullable=True)
    fip_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The staleness detector (§1.7): copy of `fips.updated_at` at projection
    # time -- a mismatch against the live `fips` row means the projection is
    # behind.
    fip_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    projection_epoch: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_facets_source_updated", "source", "fip_updated_at"),
        Index("ix_facets_km", "questionnaire_id", "questionnaire_version"),
        Index("ix_facets_epoch", "projection_epoch"),
        Index("ix_facets_stale", "projected_at"),
    )


class FipCell(Base):
    """The matrix cell, materialised (spec §1.3): grain (fip_id,
    question_id), one row per question of the FIP's own questionnaire,
    answered or not. `hidden: true` questions get no row at all (matches the
    RDF export). Four covering indexes so coverage/gaps never touch the
    table heap."""

    __tablename__ = "fip_cells"

    fip_id: Mapped[str] = mapped_column(String, primary_key=True)
    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    principle: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_principle: Mapped[str | None] = mapped_column(String, nullable=True)
    principle_group: Mapped[str] = mapped_column(String, nullable=False)
    principle_known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope: Mapped[str | None] = mapped_column(String, nullable=True)
    fer_type: Mapped[str | None] = mapped_column(String, nullable=True)
    cell_state: Mapped[str] = mapped_column(String, nullable=False)
    decl_count: Mapped[int] = mapped_column(Integer, nullable=False)
    current_count: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    none_count: Mapped[int] = mapped_column(Integer, nullable=False)
    not_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # spec 12 §B3: highest assurance level over this cell's declarations;
    # NULL until §B3 lands.
    max_assurance: Mapped[str | None] = mapped_column(String, nullable=True)
    # spec 12 §A3: 0 until §A3 lands.
    coherence_flags: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # spec 12 §A2: false until §A2 lands.
    type_mismatch_ack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_cells_q_state", "question_id", "cell_state", "fip_id"),
        Index("ix_cells_subp_state", "sub_principle", "cell_state", "fip_id"),
        Index("ix_cells_fertype_state", "fer_type", "cell_state", "fip_id"),
    )


class FipDeclaration(Base):
    """One row per stored declaration (spec §1.4): grain (fip_id,
    question_id, decl_index) -- what adoption, evolution, the inverted index
    and similarity read. `fer_key` is the convergence key (§1.5), the
    leading column of `ix_decl_ferkey_q_fip`, deliberately: candidate
    generation (§4.3, brief B) is a range scan on one value per key."""

    __tablename__ = "fip_declarations"

    fip_id: Mapped[str] = mapped_column(String, primary_key=True)
    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    decl_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    principle: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_principle: Mapped[str | None] = mapped_column(String, nullable=True)
    principle_group: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str | None] = mapped_column(String, nullable=True)
    fer_type: Mapped[str | None] = mapped_column(String, nullable=True)
    fer_key: Mapped[str] = mapped_column(String, nullable=False)
    fer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    free_text_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    successor_fer_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # spec 12 §B3: 'declared' | 'evidenced'; NULL when unknown.
    assurance_level: Mapped[str | None] = mapped_column(String, nullable=True)
    has_note: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("ix_decl_ferkey_q_fip", "fer_key", "question_id", "fip_id"),
        Index("ix_decl_status_ferkey_fip", "status", "fer_key", "fip_id"),
        Index("ix_decl_q_status_ferkey", "question_id", "status", "fer_key", "fip_id"),
        Index("ix_decl_succ", "successor_fer_key", "fip_id"),
        Index("ix_decl_fer_id", "fer_id", "fip_id"),
    )


class FerKeyDf(Base):
    """spec §4.3: document frequency per `(question_id, fer_key)`, a
    heuristic for candidate-generation ordering only (a wrong count costs
    candidates, never correctness). Declared here (brief A, so `create_all`
    ships the table with schema v8); maintained incrementally by
    `reproject_fip`/`unproject_fip` and rebuilt by `backfill-declarations` in
    brief B, which also adds the similarity code that reads it."""

    __tablename__ = "fer_key_df"

    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    fer_key: Mapped[str] = mapped_column(String, primary_key=True)
    df_all: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    df_public: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DashboardPopulation(Base):
    """A saved, shareable population query (spec §2.1). `hash` already
    includes `auth_scope` (§2.3), so two viewers with different rights on
    the same spec never collide on one row."""

    __tablename__ = "dashboard_populations"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    auth_scope: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_dashpop_owner", "owner_id", "created_at"),)


class DashboardMeta(Base):
    """A tiny key/value store -- `dashboard_meta['projection_epoch']` (bumped
    on a knowledge-model content edit, part of every ETag) and
    `dashboard_meta['reprojection_backlog']` (a JSON list of affected
    questionnaire refs, drained by `backfill-declarations --only-stale`),
    per spec §1.6/§1.8. One row per key; `value` holds whatever JSON shape
    that key needs (an int, a list, ...)."""

    __tablename__ = "dashboard_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)


# ---------------------------------------------------------------------------
# v8, brief B (spec 13-fip-dashboard.md §10.2): MinHash signatures/bands and
# hot-bucket bookkeeping (§4.2/§4.4), network shadow-FIP identity (§5.4) and
# the snapshot tier (§5.1). `fipm.projection` writes `FipSignature`/
# `FipSignatureBand`; `fipm.dashboard.similarity_views` writes
# `LshHotBucket` (the refresh job); `fipm.network_ingest` writes
# `NetworkFip`; `fipm.dashboard.snapshots` owns `DashboardSnapshot`.
# ---------------------------------------------------------------------------


class FipSignature(Base):
    """spec §4.2: one MinHash signature per FIP, `K` big-endian uint32
    packed into `signature` (512 bytes at K=128). `k`/`bands`/`rows_per_band`
    are stored alongside the blob so `check-declarations` can detect a
    signature computed under different LSH parameters (a settings change)
    without having to guess from the blob's length alone."""

    __tablename__ = "fip_signatures"

    fip_id: Mapped[str] = mapped_column(String, primary_key=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    bands: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_per_band: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FipSignatureBand(Base):
    """spec §4.2: one row per `(fip_id, band_index)` -- the LSH bucket
    membership. `ix_bands_bucket` is the covering index the candidate-pair
    self-join (§4.4) and the neighbour-free clustering path both scan."""

    __tablename__ = "fip_signature_bands"

    fip_id: Mapped[str] = mapped_column(String, primary_key=True)
    band_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    band_hash: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (Index("ix_bands_bucket", "band_index", "band_hash", "fip_id"),)


class LshHotBucket(Base):
    """spec §4.4: a band bucket whose membership exceeds
    `FIPM_DASHBOARD_LSH_BUCKET_MAX`, maintained by the refresh job (never
    computed per-request) -- excluded from the candidate-pair join and
    surfaced instead as one pre-formed cluster (the guard against a bucket
    of near-identical FIPs emitting O(m^2) pairs)."""

    __tablename__ = "lsh_hot_buckets"

    band_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    band_hash: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    representative_fip_id: Mapped[str] = mapped_column(String, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NetworkFip(Base):
    """spec §5.4: a read-only shadow identity for a nanopublication-network
    community's FIP, ingested by `python -m fipm ingest-network-fips`.
    **Not** a `fips` row -- `fip_id` is `'net:' + sha256(community_iri)[:22]`,
    a namespace that never collides with a real `fips.id` (spec 01's ids are
    ULID-shaped, never `net:`-prefixed), so a network shadow row can be
    joined into `fip_facets`/`fip_cells`/`fip_declarations`/`fip_signatures`/
    `fip_signature_bands` by `fip_id` with no risk of aliasing a real FIP.
    `fetched_at` feeds the population's `source_max_updated_at` (§5.3's
    staleness detector) exactly as `fips.updated_at` does for a local FIP."""

    __tablename__ = "network_fips"

    fip_id: Mapped[str] = mapped_column(String, primary_key=True)
    community_iri: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    fip_nanopub_iri: Mapped[str | None] = mapped_column(String, nullable=True)
    index_iri: Mapped[str | None] = mapped_column(String, nullable=True)
    created: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    questionnaire_id: Mapped[str | None] = mapped_column(String, nullable=True)
    questionnaire_version: Mapped[str | None] = mapped_column(String, nullable=True)


class DashboardSnapshot(Base):
    """spec §5.1: a computed view payload, keyed `(population_hash, view,
    params_hash)`. `payload` is the `data` object of §3's envelope,
    verbatim -- `fipm.dashboard.snapshots.get_or_compute` is the only writer
    and the only freshness-checker (§5.3's four staleness conditions)."""

    __tablename__ = "dashboard_snapshots"

    population_hash: Mapped[str] = mapped_column(String, primary_key=True)
    view: Mapped[str] = mapped_column(String, primary_key=True)
    params_hash: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # 'fresh' | 'computing' | 'failed'
    payload: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    payload_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    etag: Mapped[str] = mapped_column(String, nullable=False)
    fip_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_max_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    projection_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("ix_snap_expires", "expires_at"),)
