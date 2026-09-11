"""spec 13-fip-dashboard.md §1: the derived, write-maintained projection of
`Fip.answers` -- `fip_facets` / `fip_cells` / `fip_declarations` -- that
every dashboard view reads. `json_extract` over a 100k-row JSON column is a
full scan of wide, JSON-bearing pages, SQLite-only, and unindexable; this
module keeps that scan out of every hot path by maintaining a normalised,
by-column projection instead (§1.1).

Two halves:

- **Pure** (`convergence_key`, `project_answers`): no DB, no FastAPI. This is
  the *one* function the §1.8 degrade-ladder fallback and the write-path
  projection both call, so the two can never disagree.
- **Stateful** (`reproject_fip`, `unproject_fip`, `register_projection_hooks`,
  `projection_suspended`, `stale_fip_ids`): the ORM-level write hook (D3) and
  the CLI's bulk-write escape hatch.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, attributes

from fipm import similarity
from fipm.config import get_settings
from fipm.models import (
    DashboardMeta,
    FerKeyDf,
    Fip,
    FipCell,
    FipDeclaration,
    FipFacets,
    FipSignature,
    FipSignatureBand,
    KnowledgeModel,
)

# Deliberately *not* a module-level `from fipm.rdf import ...`: fipm.rdf pulls
# in fipm.exporters -> fipm.authz -> fipm.db, and fipm.db registers this
# module's hooks on SessionLocal at *its own* import time (fipm.db.
# register_projection_hooks(SessionLocal), right after SessionLocal is
# defined) -- a module-level import here would make that a circular import
# (fipm.db -> fipm.projection -> fipm.rdf -> fipm.exporters -> fipm.authz ->
# fipm.db, mid-initialisation). The three names below are looked up lazily,
# inside the functions that need them, instead.

PLANNED_STATUSES = frozenset({"planned", "planned-development", "planned-replacement"})

# The six-value `cell_state` enum, precedence exactly per spec §1.3.
CELL_STATES: tuple[str, ...] = (
    "current",
    "planned",
    "none",
    "not-applicable",
    "unanswered",
    "absent",
)

# A re-entrancy / suspend flag lives in `session.info` (per-Session, not
# module-global) so two Sessions in the same process (e.g. a test and the
# app under test) never share suspension state. This ContextVar is only used
# by `projection_suspended()` as the *default* value new Sessions read --
# see its docstring.
_suspended_by_default: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "fipm_projection_suspended_default", default=False
)


def convergence_key(fer_id: str | None, fer_free_text: str | None, status: str) -> str:
    """spec §1.5, THE convergence key, reused verbatim by every reader:

        fer_key = fer_id                                 if the declaration has a ferId
                = 'text:' + normalise(fer_free_text)      otherwise, if it has free text
                = 'none:' + status                        otherwise (a bare `none`)

    `normalise` delegates to `fipm.rdf.normalise_free_text` -- the same
    normalisation `frontend/src/lib/matrix.ts::normaliseFreeText` and
    `fipm.rdf._free_text_hash` use, so all three agree on what "the same
    resource" is. No third identity rule may be introduced anywhere in this
    module."""
    if fer_id:
        return fer_id
    if fer_free_text:
        from fipm.rdf import normalise_free_text

        return f"text:{normalise_free_text(fer_free_text)}"
    return f"none:{status}"


def _successor_key(decl: dict[str, Any]) -> str | None:
    """Same rule as `convergence_key`, but for the successor fields -- `None`
    (not `'none:<status>'`) when neither `successorFerId` nor
    `successorFreeText` is set, i.e. "no successor", not "a bare none"."""
    successor_id = decl.get("successorFerId")
    successor_text = decl.get("successorFreeText")
    if not successor_id and not successor_text:
        return None
    return convergence_key(successor_id, successor_text, decl.get("status") or "")


@dataclass(frozen=True)
class ProjectedQuestion:
    question_id: str
    question_index: int
    principle: str | None
    sub_principle: str | None
    principle_group: str
    principle_known: bool
    scope: str | None
    fer_type: str | None


@dataclass(frozen=True)
class ProjectedCell:
    question_id: str
    question_index: int
    principle: str | None
    sub_principle: str | None
    principle_group: str
    principle_known: bool
    scope: str | None
    fer_type: str | None
    cell_state: str
    decl_count: int
    current_count: int
    planned_count: int
    none_count: int
    not_applicable: bool


@dataclass(frozen=True)
class ProjectedDeclaration:
    question_id: str
    decl_index: int
    principle: str | None
    sub_principle: str | None
    principle_group: str
    scope: str | None
    fer_type: str | None
    fer_key: str
    fer_id: str | None
    free_text_hash: str | None
    status: str
    successor_fer_key: str | None
    has_note: bool


@dataclass(frozen=True)
class ProjectedFip:
    """Everything `project_answers` can derive from a knowledge model's
    `content` and one FIP's `answers` alone -- no `Fip` row, no DB. The §1.8
    degrade-ladder fallback and `reproject_fip` both call this and nothing
    else to get cells/declarations, so they cannot disagree."""

    cells: list[ProjectedCell] = field(default_factory=list)
    declarations: list[ProjectedDeclaration] = field(default_factory=list)
    question_count: int = 0
    answered_questions: int = 0
    not_applicable_questions: int = 0
    declaration_count: int = 0
    current_declarations: int = 0
    token_count: int = 0


def _iter_questions(km_content: dict[str, Any] | None) -> list[ProjectedQuestion]:
    """Non-`hidden` questions of a knowledge model's `content`, in
    section/question order, each carrying the cell-level metadata every
    question of this FIP's own questionnaire needs -- `question_index` is
    the position among *visible* questions only, so it matches what
    `fip_cells` actually holds."""
    from fipm.rdf import KNOWN_PRINCIPLE_IDS

    out: list[ProjectedQuestion] = []
    index = 0
    for section in (km_content or {}).get("sections", []):
        for question in section.get("questions", []):
            if question.get("hidden") is True:
                continue
            sub_principle = question.get("principle")
            principle = sub_principle.split(".")[0] if sub_principle else None
            principle_group = sub_principle[0] if sub_principle else "Other"
            out.append(
                ProjectedQuestion(
                    question_id=question["id"],
                    question_index=index,
                    principle=principle,
                    sub_principle=sub_principle,
                    principle_group=principle_group,
                    principle_known=sub_principle in KNOWN_PRINCIPLE_IDS,
                    scope=question.get("scope"),
                    fer_type=question.get("ferType"),
                )
            )
            index += 1
    return out


def project_answers(
    km_content: dict[str, Any] | None, answers: list[dict[str, Any]] | None
) -> ProjectedFip:
    """**Pure.** The one function that turns a knowledge model's `content`
    and one FIP's `answers` (the exact JSON shape stored on `Fip.answers`)
    into the cell/declaration rows the projection tables (and the §1.8
    degrade-ladder fallback) hold. No DB access, no FastAPI import."""
    from fipm.rdf import _free_text_hash

    questions = _iter_questions(km_content)
    answers_by_qid = {a.get("questionId"): a for a in (answers or []) if a.get("questionId")}

    cells: list[ProjectedCell] = []
    declarations: list[ProjectedDeclaration] = []
    answered_questions = 0
    not_applicable_questions = 0
    declaration_count = 0
    current_declarations = 0
    tokens: set[str] = set()

    for q in questions:
        answer = answers_by_qid.get(q.question_id)
        decls = (answer or {}).get("declarations") or []
        not_applicable = bool((answer or {}).get("notApplicable"))

        current_count = sum(1 for d in decls if d.get("status") == "current")
        planned_count = sum(1 for d in decls if d.get("status") in PLANNED_STATUSES)
        none_count = sum(1 for d in decls if d.get("status") == "none")

        if current_count > 0:
            cell_state = "current"
        elif planned_count > 0:
            cell_state = "planned"
        elif decls:
            cell_state = "none"
        elif not_applicable:
            cell_state = "not-applicable"
        else:
            cell_state = "unanswered"

        if cell_state != "unanswered":
            answered_questions += 1
        if cell_state == "not-applicable":
            not_applicable_questions += 1
            tokens.add(f"{q.question_id}\x1fNA")

        cells.append(
            ProjectedCell(
                question_id=q.question_id,
                question_index=q.question_index,
                principle=q.principle,
                sub_principle=q.sub_principle,
                principle_group=q.principle_group,
                principle_known=q.principle_known,
                scope=q.scope,
                fer_type=q.fer_type,
                cell_state=cell_state,
                decl_count=len(decls),
                current_count=current_count,
                planned_count=planned_count,
                none_count=none_count,
                not_applicable=not_applicable,
            )
        )

        for decl_index, decl in enumerate(decls):
            fer_id = decl.get("ferId")
            fer_free_text = decl.get("ferFreeText")
            status = decl.get("status") or ""
            fer_key = convergence_key(fer_id, fer_free_text, status)
            declarations.append(
                ProjectedDeclaration(
                    question_id=q.question_id,
                    decl_index=decl_index,
                    principle=q.principle,
                    sub_principle=q.sub_principle,
                    principle_group=q.principle_group,
                    scope=q.scope,
                    fer_type=q.fer_type,
                    fer_key=fer_key,
                    fer_id=fer_id,
                    free_text_hash=_free_text_hash(fer_free_text) if fer_free_text else None,
                    status=status,
                    successor_fer_key=_successor_key(decl),
                    has_note=bool(decl.get("note")),
                )
            )
            declaration_count += 1
            if status == "current":
                current_declarations += 1
                tokens.add(f"{q.question_id}\x1f{fer_key}")

    return ProjectedFip(
        cells=cells,
        declarations=declarations,
        question_count=len(questions),
        answered_questions=answered_questions,
        not_applicable_questions=not_applicable_questions,
        declaration_count=declaration_count,
        current_declarations=current_declarations,
        token_count=len(tokens),
    )


# ---------------------------------------------------------------------------
# Stateful half: DB writes, the ORM hook, suspension.
# ---------------------------------------------------------------------------


def _get_projection_epoch(session: Session) -> int:
    row = session.get(DashboardMeta, "projection_epoch")
    return int(row.value) if row is not None else 0


def current_fer_key_pairs(declarations: list[Any]) -> set[tuple[str, str]]:
    """spec §4.3: `fer_key_df` counts *current* declarations only -- it
    exists purely to order candidate generation, so `sign`ed increments
    below only ever touch `current` keys. `declarations` is duck-typed:
    either `ProjectedDeclaration` (brief write path) or a stored
    `FipDeclaration` row (unproject's read of the *old* state) -- both carry
    `.question_id`/`.fer_key`/`.status`. Public: also used by
    `fipm.network_ingest` (network shadow rows have no `Fip`/`reproject_fip`
    path of their own, §5.4)."""
    return {(d.question_id, d.fer_key) for d in declarations if d.status == "current"}


def bump_fer_key_df(session: Session, declarations: list[Any], *, sign: int, public: bool) -> None:
    """spec §4.3: `fer_key_df` is a **heuristic for candidate-generation
    ordering only** ("a wrong count costs candidates, never correctness"),
    so this deliberately does not try to reconstruct a FIP's *historical*
    visibility at decrement time -- both the decrement (old declarations,
    in `unproject_fip`) and the increment (new declarations, in
    `reproject_fip`) use whatever `fip.visibility` reads *now* (the two
    calls happen back-to-back inside the same delete-then-insert, so the
    only case they can disagree is a PATCH that changes `answers` and
    `visibility` in the same request, which very slightly under/over-counts
    `df_public` for that one write -- self-correcting on the FIP's next
    edit). Clamped at 0: never goes negative even if two writes interleave
    in a way this table's optimistic bookkeeping doesn't perfectly track.
    Public: `fipm.network_ingest` calls this too, with `public=True` always
    (network shadow rows are public nanopublications by construction)."""
    for question_id, fer_key in current_fer_key_pairs(declarations):
        row = session.get(FerKeyDf, (question_id, fer_key))
        if row is None:
            if sign <= 0:
                continue
            row = FerKeyDf(question_id=question_id, fer_key=fer_key, df_all=0, df_public=0)
            session.add(row)
            # A brand-new key must be visible to `session.get()` before this
            # function runs again for a *different* FIP later in the same
            # transaction (e.g. a bulk import committing many new FIPs at
            # once, all introducing the same new key) -- a pending (never
            # flushed) object is invisible to `Session.get()`, so two FIPs
            # in one transaction both "discovering" the same new key would
            # otherwise each `session.add()` their own row and collide on
            # the primary key at flush time. `SessionLocal` is
            # `autoflush=False` (fipm.db), so this flush is this function's
            # own responsibility, not implicit.
            session.flush()
        row.df_all = max(0, row.df_all + sign)
        if public:
            row.df_public = max(0, row.df_public + sign)


def write_signature_rows(
    session: Session,
    fip_id: str,
    cells: list[Any],
    declarations: list[Any],
    *,
    computed_at: datetime | None = None,
) -> None:
    """spec §4.2: one MinHash signature + `LSH_BANDS` band rows for
    `fip_id`, from its own cells/declarations. Shared by `reproject_fip`
    (local FIPs, inside the write hook's transaction) and
    `fipm.network_ingest` (network shadow rows, which have no `Fip` row and
    so cannot go through `reproject_fip` at all) -- both must use the exact
    same parameters and hashing, or a local/network similarity comparison
    (test 37) would be comparing signatures computed two different ways."""
    settings = get_settings()
    token_set = similarity.tokens(cells, declarations)
    signature_bytes = similarity.minhash(
        token_set, k=settings.dashboard_lsh_k, seed=settings.dashboard_lsh_seed
    )
    band_hashes = similarity.bands(
        signature_bytes,
        n_bands=settings.dashboard_lsh_bands,
        rows_per_band=settings.dashboard_lsh_rows,
    )
    session.add(
        FipSignature(
            fip_id=fip_id,
            token_count=len(token_set),
            k=settings.dashboard_lsh_k,
            bands=settings.dashboard_lsh_bands,
            rows_per_band=settings.dashboard_lsh_rows,
            signature=signature_bytes,
            computed_at=computed_at or datetime.now(UTC),
        )
    )
    for band_index, band_hash in enumerate(band_hashes):
        session.add(FipSignatureBand(fip_id=fip_id, band_index=band_index, band_hash=band_hash))


def delete_signature_rows(session: Session, fip_id: str) -> None:
    session.execute(delete(FipSignature).where(FipSignature.fip_id == fip_id))
    session.execute(delete(FipSignatureBand).where(FipSignatureBand.fip_id == fip_id))


def unproject_fip(session: Session, fip_id: str) -> None:
    """Delete every projection row for `fip_id` -- used both by
    `reproject_fip` (delete-then-insert) and directly when a FIP is deleted
    or a rolled-back write must leave nothing behind. Reads the *old*
    `fip_declarations` rows first so `fer_key_df` (§4.3) can be decremented
    -- a heuristic table, so this is best-effort, not authorization-bearing
    (D2 still holds: nothing here is ever consulted for a security
    decision)."""
    old_declarations = list(
        session.execute(
            select(FipDeclaration.question_id, FipDeclaration.fer_key, FipDeclaration.status).where(
                FipDeclaration.fip_id == fip_id
            )
        )
    )
    if old_declarations:
        fip = session.get(Fip, fip_id)
        was_public = bool(fip is not None and fip.visibility == "public")
        bump_fer_key_df(session, old_declarations, sign=-1, public=was_public)

    session.execute(delete(FipCell).where(FipCell.fip_id == fip_id))
    session.execute(delete(FipDeclaration).where(FipDeclaration.fip_id == fip_id))
    session.execute(delete(FipFacets).where(FipFacets.fip_id == fip_id))
    delete_signature_rows(session, fip_id)


def reproject_fip(session: Session, fip_id: str) -> None:
    """Delete-then-insert the full projection for one FIP, inside the
    caller's transaction (no `session.commit()` here -- the caller's own
    commit, or the write hook's `before_commit`, does that). A FIP that no
    longer exists (deleted earlier in the same flush) is simply unprojected;
    a FIP whose knowledge model can't be found leaves an empty projection
    (0 cells/declarations) rather than raising, since a dangling
    questionnaire ref must not block every other write in the same
    transaction."""
    unproject_fip(session, fip_id)

    fip = session.get(Fip, fip_id)
    if fip is None:
        return

    km = session.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    projected = project_answers(km.content if km else None, fip.answers)
    epoch = _get_projection_epoch(session)
    now = datetime.now(UTC)
    migrated_from = fip.migrated_from or {}

    session.add(
        FipFacets(
            fip_id=fip.id,
            source="local",
            questionnaire_id=fip.questionnaire_id,
            questionnaire_version=fip.questionnaire_version,
            area_key=f"{fip.questionnaire_id}@{fip.questionnaire_version}",
            language=fip.language,
            question_count=projected.question_count,
            answered_questions=projected.answered_questions,
            not_applicable_questions=projected.not_applicable_questions,
            declaration_count=projected.declaration_count,
            current_declarations=projected.current_declarations,
            token_count=projected.token_count,
            migrated_from_id=migrated_from.get("id"),
            migrated_from_version=migrated_from.get("version"),
            fip_created_at=fip.created_at,
            fip_updated_at=fip.updated_at,
            projected_at=now,
            projection_epoch=epoch,
        )
    )
    for cell in projected.cells:
        session.add(
            FipCell(
                fip_id=fip.id,
                question_id=cell.question_id,
                question_index=cell.question_index,
                principle=cell.principle,
                sub_principle=cell.sub_principle,
                principle_group=cell.principle_group,
                principle_known=cell.principle_known,
                scope=cell.scope,
                fer_type=cell.fer_type,
                cell_state=cell.cell_state,
                decl_count=cell.decl_count,
                current_count=cell.current_count,
                planned_count=cell.planned_count,
                none_count=cell.none_count,
                not_applicable=cell.not_applicable,
            )
        )
    for decl in projected.declarations:
        session.add(
            FipDeclaration(
                fip_id=fip.id,
                question_id=decl.question_id,
                decl_index=decl.decl_index,
                principle=decl.principle,
                sub_principle=decl.sub_principle,
                principle_group=decl.principle_group,
                scope=decl.scope,
                fer_type=decl.fer_type,
                fer_key=decl.fer_key,
                fer_id=decl.fer_id,
                free_text_hash=decl.free_text_hash,
                status=decl.status,
                successor_fer_key=decl.successor_fer_key,
                assurance_level=None,
                has_note=decl.has_note,
            )
        )

    # spec §4.2: signature + 32 band rows, written in the same delete-then-
    # insert (1-2 ms per FIP, inside the write hook's 10 ms budget, §4.2).
    write_signature_rows(session, fip.id, projected.cells, projected.declarations, computed_at=now)

    # spec §4.3: fer_key_df's increment half (the decrement already ran
    # inside `unproject_fip` above, over the *old* declarations).
    bump_fer_key_df(session, projected.declarations, sign=1, public=(fip.visibility == "public"))


class _ProjectionSuspended:
    """`with projection_suspended():` turns the write hook into a no-op for
    the duration of the block, in *this* (contextvars-based, so it is safe
    across `await` points and does not leak into unrelated concurrent
    requests) context -- for the backfill CLI and `_cmd_purge_standalone_
    fips`, which write/delete cells/declarations in bulk themselves and
    would otherwise redo the same work once per FIP via the hook.
    `FIPM_DASHBOARD_ENABLED=false` (§7.3) is a *separate* kill switch,
    checked fresh on every hook invocation via `_hooks_enabled()` (not tied
    to this context manager), so flipping the setting takes effect on the
    very next write with no process restart needed."""

    def __enter__(self) -> _ProjectionSuspended:
        self._token = _suspended_by_default.set(True)
        return self

    def __exit__(self, *exc: object) -> None:
        _suspended_by_default.reset(self._token)


def projection_suspended() -> _ProjectionSuspended:
    return _ProjectionSuspended()


def _hooks_enabled() -> bool:
    if _suspended_by_default.get():
        return False
    return get_settings().dashboard_enabled


def _collect_dirty(
    session: Session, dirty_ids: set[str], deleted_ids: set[str], epoch_bump: set[tuple[str, str]]
) -> None:
    """Scans the session's *current* `new`/`dirty`/`deleted` collections and
    adds what it finds to the three accumulator sets, in place."""
    for obj in session.new | session.dirty:
        if isinstance(obj, Fip):
            dirty_ids.add(obj.id)
    for obj in session.deleted:
        if isinstance(obj, Fip):
            deleted_ids.add(obj.id)
            dirty_ids.discard(obj.id)
    for obj in session.dirty:
        if isinstance(obj, KnowledgeModel):
            # Only a real edit to `content` invalidates every projection row
            # keyed on this knowledge-model version -- a KM's other columns
            # (visibility, status, ...) change far more often and must not
            # bump the epoch (spec §1.6).
            history = attributes.get_history(obj, "content")
            if history.has_changes():
                epoch_bump.add((obj.id, obj.version))


def _before_flush(session: Session, _flush_context: object, _instances: object) -> None:
    """Accumulates dirty/deleted `Fip` ids (and `KnowledgeModel` content
    edits) into `session.info`, across however many flushes happen before
    the eventual commit -- belt-and-braces for the (currently theoretical,
    no router does it today) case of an explicit mid-transaction
    `session.flush()` that would otherwise transition a newly added `Fip`
    from "pending" to "persistent, unchanged" and so drop out of
    `session.new`/`session.dirty` before `before_commit` ever looks."""
    if not _hooks_enabled() or session.info.get("fipm_projection_in_progress"):
        return
    dirty_ids: set[str] = session.info.setdefault("fipm_projection_dirty", set())
    deleted_ids: set[str] = session.info.setdefault("fipm_projection_deleted", set())
    epoch_bump: set[tuple[str, str]] = session.info.setdefault("fipm_projection_epoch_bump", set())
    _collect_dirty(session, dirty_ids, deleted_ids, epoch_bump)


def _before_commit(session: Session) -> None:
    """D3's write hook. **Deviation from the spec's `after_flush`/
    `before_commit` split, recorded here and in the brief-A report:**
    measured against this SQLAlchemy version, `Session.commit()` fires
    `before_commit` *before* the commit's own implicit flush (and therefore
    before `before_flush`/`after_flush`) -- so an `after_flush`-only
    accumulator would always be one commit() call behind, never reprojecting
    inside the write it belongs to. Instead: `before_commit` reads
    `session.new`/`session.dirty`/`session.deleted` directly (still fully
    populated at this point, confirmed empirically), unions that with
    whatever `_before_flush` already accumulated from any earlier flush in
    this same transaction, processes deletions, *then* flushes the caller's
    own pending changes (so `reproject_fip`'s `session.get()` lookups see
    them -- `Session.get()` does not see a still-pending, unflushed object)
    before reprojecting the dirty ones. Everything below still executes
    inside the caller's transaction: nothing here calls `session.commit()`,
    only `session.flush()`, so a subsequent `session.rollback()` (e.g. the
    `_insert_fip` id-collision retry loop, or a test-injected IntegrityError)
    undoes it exactly like every other pending write.

    **Deleted ids are unprojected *before* the flush, deliberately**
    (spec §4.3): `unproject_fip` reads the FIP's current `visibility` (to
    decrement `fer_key_df.df_public`) via `session.get(Fip, fip_id)` -- an
    object pending deletion is still in the identity map with its
    attributes intact until the flush actually issues its `DELETE`, but
    would read back as gone (or force a premature autoflush) afterwards.
    `SessionLocal` is `autoflush=False` (fipm.db), so `unproject_fip`'s own
    `session.execute()` calls here do not trigger that flush early."""
    if not _hooks_enabled():
        return
    if session.info.get("fipm_projection_in_progress"):
        return  # re-entrancy guard: reproject_fip's own session.add()s must not re-trigger this

    dirty_ids: set[str] = session.info.pop("fipm_projection_dirty", set())
    deleted_ids: set[str] = session.info.pop("fipm_projection_deleted", set())
    epoch_bump: set[tuple[str, str]] = session.info.pop("fipm_projection_epoch_bump", set())
    _collect_dirty(session, dirty_ids, deleted_ids, epoch_bump)

    if not dirty_ids and not deleted_ids and not epoch_bump:
        return

    session.info["fipm_projection_in_progress"] = True
    try:
        for fip_id in deleted_ids:
            unproject_fip(session, fip_id)
        session.flush()
        for fip_id in dirty_ids:
            reproject_fip(session, fip_id)
        if epoch_bump:
            row = session.get(DashboardMeta, "projection_epoch")
            if row is None:
                row = DashboardMeta(key="projection_epoch", value=0)
                session.add(row)
            row.value = int(row.value or 0) + 1

            backlog_row = session.get(DashboardMeta, "reprojection_backlog")
            existing = list(backlog_row.value) if backlog_row is not None else []
            for km_id, km_version in epoch_bump:
                ref = f"{km_id}@{km_version}"
                if ref not in existing:
                    existing.append(ref)
            if backlog_row is None:
                session.add(DashboardMeta(key="reprojection_backlog", value=existing))
            else:
                backlog_row.value = existing
    finally:
        session.info["fipm_projection_in_progress"] = False


def register_projection_hooks(session_factory: object) -> None:
    """Registers the write hook (D3) on every `Session` created by
    `session_factory` (a `sessionmaker`) -- see `_before_commit`'s docstring
    for the exact mechanics and why `before_flush` (not `after_flush`) is
    the accumulator. The whole projection lands inside the caller's own
    transaction. Idempotent: safe to call more than once -- SQLAlchemy's
    `event.contains`/`event.listen` on the same target/identifier/fn triple
    only de-duplicates when the exact same function object is passed, which
    module-level functions guarantee."""
    from sqlalchemy import event

    if not event.contains(session_factory, "before_flush", _before_flush):
        event.listen(session_factory, "before_flush", _before_flush)
    if not event.contains(session_factory, "before_commit", _before_commit):
        event.listen(session_factory, "before_commit", _before_commit)


def stale_fip_ids(session: Session, limit: int | None = None) -> list[str]:
    """spec §1.7's `--only-stale` predicate: `fips.id` with no `fip_facets`
    row, or `updated_at > fip_facets.fip_updated_at`, or
    `fip_facets.projection_epoch < dashboard_meta['projection_epoch']`, or
    whose questionnaire ref is in `reprojection_backlog`."""
    from sqlalchemy import select

    epoch = _get_projection_epoch(session)
    backlog_row = session.get(DashboardMeta, "reprojection_backlog")
    backlog = set(backlog_row.value) if backlog_row is not None else set()

    facets_by_id = {row.fip_id: row for row in session.query(FipFacets).all()}
    stmt = select(Fip.id, Fip.updated_at, Fip.questionnaire_id, Fip.questionnaire_version)
    ids: list[str] = []
    for fip_id, updated_at, km_id, km_version in session.execute(stmt):
        facets = facets_by_id.get(fip_id)
        ref = f"{km_id}@{km_version}"
        if (
            facets is None
            or updated_at > facets.fip_updated_at
            or facets.projection_epoch < epoch
            or ref in backlog
        ):
            ids.append(fip_id)
            if limit is not None and len(ids) >= limit:
                break
    return ids
