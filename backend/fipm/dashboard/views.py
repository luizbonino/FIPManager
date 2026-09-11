"""spec 13-fip-dashboard.md §3.1/§3.2/§3.4/§3.5: coverage, adoption, gaps and
evolution -- brief A's four views. Each is `(population resolution) + (one
aggregate statement)`, exactly, on the live (T1) path (AC-16); above T1 or
when the population's projection is stale/missing, the §1.8 degrade ladder
takes over -- small populations recompute in Python via
`fipm.projection.project_answers` (the *same* function the write hook uses,
so the two can never disagree), large ones refuse with `409`.

Brief B (spec §5): the T1/T2 tier decision has moved out of this module --
`fipm.dashboard.snapshots.get_or_compute` resolves the population once,
decides whether it is within `FIPM_DASHBOARD_LIVE_MAX_CELLS`, and only then
calls the view function below (passing its own already-resolved population
via `pop=`, so resolution never runs twice). A view function here has no
size ceiling of its own any more -- it will happily compute an aggregate
over an arbitrarily large population if asked to (that is exactly what the
snapshot layer does once, synchronously, to produce a T2 snapshot); only
**staleness** (`_check_staleness`) can still make it refuse.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fipm.config import get_settings
from fipm.dashboard import DashboardError
from fipm.dashboard.populations import (
    ResolvedPopulation,
    auth_scope_for,
    canonicalise_spec,
    check_k_anonymity,
    population_hash,
    resolve_population,
)
from fipm.dashboard.snapshots import params_hash as snapshot_params_hash
from fipm.models import Fer, Fip, FipCell, FipDeclaration, FipFacets, KnowledgeModel, User
from fipm.projection import PLANNED_STATUSES, project_answers

CELL_STATE_JSON_KEYS = {
    "current": "current",
    "planned": "planned",
    "none": "none",
    "not-applicable": "notApplicable",
    "unanswered": "unanswered",
    "absent": "absent",
}
EMPTY_COUNTS: dict[str, int] = dict.fromkeys(CELL_STATE_JSON_KEYS.values(), 0)

# Assumed average questions-per-FIP for the T1 cell-count estimate, absent an
# extra statement to compute it exactly -- 21 matches the GO FAIR mini model
# every CONFOA questionnaire is a fork of. Read by `fipm.dashboard.snapshots`
# via `estimated_cells()` below for the T1/T2/T3 tier decision.
_ASSUMED_QUESTIONS_PER_FIP = 21


# ---------------------------------------------------------------------------
# Shared: population prep, the degrade ladder, the envelope.
# ---------------------------------------------------------------------------


def _prepare_population(
    db: Session, spec: dict[str, Any], viewer: User | None
) -> ResolvedPopulation:
    pop = resolve_population(db, spec, viewer)
    check_k_anonymity(pop)
    return pop


def prepare_population(
    db: Session, spec: dict[str, Any], viewer: User | None
) -> ResolvedPopulation:
    """Public alias of `_prepare_population` -- `fipm.dashboard.snapshots`
    (brief B, spec §5) resolves the population itself exactly once (to
    decide the T1/T2/T3 tier) and hands the *same* `ResolvedPopulation` back
    into whichever view function it calls, via that function's own `pop=`
    parameter, so a snapshot-tier request never pays for population
    resolution twice."""
    return _prepare_population(db, spec, viewer)


def _stale_error(pop: ResolvedPopulation) -> DashboardError:
    if pop.unprojected_count == pop.count:
        detail = "projection_missing"
    else:
        detail = "projection_stale"
    return DashboardError(
        409,
        {
            "detail": detail,
            "staleFips": len(pop.stale_ids),
            "totalFips": pop.count,
            "hint": "python -m fipm backfill-declarations --only-stale",
        },
    )


def estimated_cells(pop: ResolvedPopulation) -> int:
    """spec §0/§7.4's T1/T2/T3 tier decisions are all in units of estimated
    `fip_cells` rows; §5.3 also uses this same estimate as (half of) the
    refresh cost model. Shared here so `fipm.dashboard.snapshots` and this
    module can never disagree on what "the population's cell count" means."""
    return pop.count * _ASSUMED_QUESTIONS_PER_FIP


def _check_staleness(pop: ResolvedPopulation) -> bool:
    """Returns `True` if the caller must take the §1.8 degraded (small
    population, Python-computed) path; raises `DashboardError` (409
    `projection_stale`/`projection_missing`) for a large stale population.
    Returns `False` when the aggregate path is safe to run.

    Brief B (spec §5): the **tier-size** decision (T1 live vs. T2 snapshot)
    no longer lives here -- it is `fipm.dashboard.snapshots.get_or_compute`'s
    job, made *before* it ever calls this view function (so a T2-tier
    population's aggregate is computed at most once, synchronously, to
    become a stored snapshot, and never in-request above
    `FIPM_DASHBOARD_SYNC_MAX_CELLS`, per AC-11). This function -- and every
    view above it -- has no size ceiling of its own; only staleness can
    still make it refuse."""
    settings = get_settings()
    if pop.stale_ids:
        if pop.count <= settings.dashboard_fallback_max_fips:
            return True
        raise _stale_error(pop)
    return False


def _envelope(
    view: str,
    spec: dict[str, Any],
    pop: ResolvedPopulation,
    data: dict[str, Any],
    *,
    viewer: User | None,
    degraded: bool,
    params_key: str = "",
) -> dict[str, Any]:
    canonical = canonicalise_spec(spec)
    # §2.3's real `auth_scope`, not a locally re-derived "pub"/"u" -- the
    # hash/ETag built from it must match the one `POST /populations` and the
    # snapshot layer (`fipm.dashboard.snapshots`) compute for the *same*
    # spec+viewer, or a saved population's hash 404s when round-tripped
    # (confirmed finding #3) and two different signed-in viewers can collide
    # on one ETag.
    scope = auth_scope_for(spec, viewer)
    phash = population_hash(canonical, scope)
    now = datetime.now(UTC)
    max_updated = max((m.updated_at for m in pop.members), default=now)
    # Confirmed finding #10: `params_key[:8]` truncated the *raw* concatenated
    # string (e.g. adoption's `f"{group_by}{status}{catalogued}{limit}
    # {offset}"`) rather than a hash of it, so two different parameter
    # combinations sharing the same first 8 characters (any two limits/
    # offsets after a long enough common prefix) produced the identical
    # ETag -- inconsistent with `snapshots.build_etag`, which hashes its
    # `params_hash` first. Hashed here the same way for consistency.
    p_hash = snapshot_params_hash({"raw": params_key})
    etag = (
        f'W/"{view}-{phash[:12]}-{p_hash[:8]}-{pop.current_epoch}-'
        f'{max_updated.isoformat()}-{pop.count}"'
    )
    return {
        "population": {
            "hash": phash,
            "authScope": scope,
            "fipCount": pop.count if pop.k_hidden == 0 else None,
            "label": None,
        },
        "tier": "live",
        "computedAt": now.isoformat().replace("+00:00", "Z"),
        "degraded": degraded,
        "degradedReason": "projection_stale" if degraded else None,
        "staleFips": len(pop.stale_ids) if degraded else None,
        "etag": etag,
        "data": data,
    }


def _km_content_cache(db: Session):
    cache: dict[tuple[str, str], dict[str, Any] | None] = {}

    def _get(km_id: str, km_version: str) -> dict[str, Any] | None:
        key = (km_id, km_version)
        if key not in cache:
            km = db.get(KnowledgeModel, key)
            cache[key] = km.content if km is not None else None
        return cache[key]

    return _get


# ---------------------------------------------------------------------------
# §3.1 Coverage
# ---------------------------------------------------------------------------

GROUP_LEVELS = ("question", "subPrinciple", "principle", "group")


def _coverage_row_key(cell_row: Any, group_by: str) -> tuple[str, str | None, str]:
    """Returns `(key, principleForDisplay, level)`."""
    if group_by == "question":
        return cell_row.question_id, cell_row.principle, "question"
    if group_by == "principle":
        key = cell_row.principle or f"q:{cell_row.question_id}"
        return key, cell_row.principle, "principle"
    if group_by == "group":
        return cell_row.principle_group, cell_row.principle, "group"
    # default: subPrinciple
    key = cell_row.sub_principle or f"q:{cell_row.question_id}"
    return key, cell_row.principle, "subPrinciple"


def _rollup_counts(
    agg_rows: list[Any], group_by: str, include_assurance: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    buckets: dict[str, dict[str, Any]] = {}
    order_hint: dict[str, int] = {}
    for row in agg_rows:
        key, principle, level = _coverage_row_key(row, group_by)
        bucket = buckets.setdefault(
            key,
            {
                "key": key,
                "level": level,
                "principle": principle,
                "principleGroup": row.principle_group,
                "questions": set(),
                "ferTypes": set(),
                "counts": dict(EMPTY_COUNTS),
                "assurance": defaultdict(int) if include_assurance else None,
            },
        )
        bucket["questions"].add(row.question_id)
        if row.fer_type:
            bucket["ferTypes"].add(row.fer_type)
        json_state = CELL_STATE_JSON_KEYS[row.cell_state]
        bucket["counts"][json_state] += row.n
        if include_assurance and getattr(row, "max_assurance", None):
            bucket["assurance"][row.max_assurance] += row.n
        order_hint[key] = min(order_hint.get(key, row.question_index), row.question_index)

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        total = sum(bucket["counts"].values())
        shares = {k: (v / total if total else 0.0) for k, v in bucket["counts"].items()}
        out = {
            "key": bucket["key"],
            "level": bucket["level"],
            "principle": bucket["principle"],
            "principleGroup": bucket["principleGroup"],
            "questions": sorted(bucket["questions"]),
            "ferTypes": sorted(bucket["ferTypes"]),
            "counts": bucket["counts"],
            "shares": shares,
        }
        if include_assurance:
            out["assurance"] = dict(bucket["assurance"])
        rows.append(out)

    order = [k for k, _ in sorted(order_hint.items(), key=lambda kv: kv[1])]
    return rows, order


def _coverage_data_from_rows(
    agg_rows: list[Any], group_by: str, include_assurance: bool, fip_count: int
) -> dict[str, Any]:
    rows, order = _rollup_counts(agg_rows, group_by, include_assurance)
    total_cells = sum(sum(r["counts"].values()) for r in rows)
    return {"rows": rows, "totals": {"fips": fip_count, "cells": total_cells}, "order": order}


def _coverage_aggregate_rows(
    db: Session, fip_ids: list[str], scope: str, include_assurance: bool
) -> list[Any]:
    cols = [
        FipCell.sub_principle,
        FipCell.principle,
        FipCell.principle_group,
        FipCell.question_id,
        FipCell.question_index,
        FipCell.scope,
        FipCell.fer_type,
        FipCell.cell_state,
    ]
    if include_assurance:
        cols.append(FipCell.max_assurance)
    cols.append(func.count().label("n"))

    stmt = select(*cols).where(FipCell.fip_id.in_(fip_ids))
    if scope in ("metadata", "data"):
        stmt = stmt.where(FipCell.scope == scope)
    group_cols = cols[:-1]
    stmt = stmt.group_by(*group_cols)
    return list(db.execute(stmt).all())


def _project_population_python(db: Session, pop: ResolvedPopulation) -> list[Any]:
    """§1.8's fallback: recompute `fip_cells`-equivalent rows for every
    member of a small, stale population in Python, via the *same*
    `project_answers` the write hook uses. Returns objects shaped enough
    like the ORM aggregate rows (attribute access) for the same rollup code
    to consume both paths."""
    from types import SimpleNamespace

    km_content = _km_content_cache(db)
    fips_by_id = {f.id: f for f in db.query(Fip).filter(Fip.id.in_(pop.fip_ids)).all()}
    out: list[Any] = []
    counter: dict[tuple, int] = defaultdict(int)
    for member in pop.members:
        fip = fips_by_id.get(member.fip_id)
        if fip is None:
            continue
        content = km_content(fip.questionnaire_id, fip.questionnaire_version)
        projected = project_answers(content, fip.answers)
        for cell in projected.cells:
            key = (
                cell.sub_principle,
                cell.principle,
                cell.principle_group,
                cell.question_id,
                cell.question_index,
                cell.scope,
                cell.fer_type,
                cell.cell_state,
            )
            counter[key] += 1
    for key, n in counter.items():
        (
            sub_principle,
            principle,
            principle_group,
            question_id,
            question_index,
            scope,
            fer_type,
            cell_state,
        ) = key
        out.append(
            SimpleNamespace(
                sub_principle=sub_principle,
                principle=principle,
                principle_group=principle_group,
                question_id=question_id,
                question_index=question_index,
                scope=scope,
                fer_type=fer_type,
                cell_state=cell_state,
                max_assurance=None,
                n=n,
            )
        )
    return out


def coverage_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    group_by: str = "subPrinciple",
    scope: str = "any",
    include_assurance: bool = False,
    pop: ResolvedPopulation | None = None,
) -> dict[str, Any]:
    if group_by not in GROUP_LEVELS:
        raise DashboardError(400, {"detail": "invalid_group_by"})
    if pop is None:
        pop = _prepare_population(db, spec, viewer)
    degraded = _check_staleness(pop)

    if not pop.fip_ids:
        data = {"rows": [], "totals": {"fips": 0, "cells": 0}, "order": []}
        return _envelope(
            "coverage",
            spec,
            pop,
            data,
            viewer=viewer,
            degraded=False,
            params_key=f"{group_by}{scope}",
        )

    if degraded:
        # `_project_population_python` already merges by the full row key
        # (scope included), so filtering by scope afterwards cannot produce
        # duplicate keys -- no re-merge needed.
        agg_rows = _project_population_python(db, pop)
        if scope in ("metadata", "data"):
            agg_rows = [r for r in agg_rows if r.scope == scope]
    else:
        agg_rows = _coverage_aggregate_rows(db, pop.fip_ids, scope, include_assurance)

    data = _coverage_data_from_rows(agg_rows, group_by, include_assurance, pop.count)
    return _envelope(
        "coverage",
        spec,
        pop,
        data,
        viewer=viewer,
        degraded=degraded,
        params_key=f"{group_by}{scope}",
    )


# ---------------------------------------------------------------------------
# §3.2 Resource adoption
# ---------------------------------------------------------------------------

ADOPTION_GROUP_BYS = ("fer", "ferType", "area", "question")


def _first_seen_free_text(db: Session, fip_ids: list[str], text_keys: list[str]) -> dict[str, str]:
    """spec §3.2: "free-text rows carry the *first* raw text seen, fetched
    with one extra bounded query over `fip_declarations` joined to `fips`
    for display only, capped at the page size." `fip_declarations` stores
    only `fer_key`/`free_text_hash`, never the raw text (D2-adjacent: the
    projection is normalised, by design), so the raw string has to come
    from `Fip.answers` -- read here as a plain ORM column (never SQL-level
    `json_extract`, satisfying AC-42) and parsed in Python, capped to a
    small, bounded row count regardless of population size."""
    from fipm.projection import convergence_key

    if not text_keys:
        text_keys = ["__none__"]  # keep the statement shape identical either way
    stmt = (
        select(FipDeclaration.question_id, Fip.answers)
        .join(Fip, Fip.id == FipDeclaration.fip_id)
        .where(FipDeclaration.fer_key.in_(text_keys), FipDeclaration.fip_id.in_(fip_ids))
        .limit(max(len(text_keys), 1) * 10)
    )
    found: dict[str, str] = {}
    remaining = set(text_keys)
    for question_id, answers in db.execute(stmt):
        if not remaining:
            break
        for answer in answers or []:
            if answer.get("questionId") != question_id:
                continue
            for decl in answer.get("declarations") or []:
                text = decl.get("ferFreeText")
                if not text:
                    continue
                key = convergence_key(decl.get("ferId"), text, decl.get("status") or "")
                if key in remaining:
                    found[key] = text
                    remaining.discard(key)
    return found


def _adoption_group_column(group_by: str):
    if group_by == "ferType":
        return FipDeclaration.fer_type
    if group_by == "question":
        return FipDeclaration.question_id
    if group_by == "area":
        return FipFacets.area_key
    return FipDeclaration.fer_key


def _adoption_aggregate_rows(
    db: Session,
    fip_ids: list[str],
    *,
    group_by: str,
    status: str,
    catalogued: str,
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    group_col = _adoption_group_column(group_by)
    # `fer_type` is the *question's* expected type (spec §1.4) -- the same
    # `fer_key` can carry a different `fer_type` per question (ORCID under an
    # identifier-service question and, in principle, elsewhere). Grouping by
    # it whenever it isn't itself the requested level would silently split
    # one FER's count across groups (a regression this file's own AC-18
    # test catches), so it is only a GROUP BY column when `groupBy=ferType`
    # or `groupBy=question` (one fer_type per question, so grouping by it
    # there is a no-op); otherwise it's an aggregate (`MIN`, any repeatable
    # representative) carried for display only.
    fer_type_is_grouped = group_by in ("ferType", "question")
    fer_type_col = (
        FipDeclaration.fer_type if fer_type_is_grouped else func.min(FipDeclaration.fer_type)
    )
    cols = [
        group_col.label("group_key"),
        FipDeclaration.fer_key,
        FipDeclaration.fer_id,
        fer_type_col.label("fer_type"),
        FipDeclaration.status,
        func.count(func.distinct(FipDeclaration.fip_id)).label("fips"),
        func.count().label("declarations"),
    ]
    stmt = select(*cols).where(FipDeclaration.fip_id.in_(fip_ids))
    if group_by == "area":
        stmt = stmt.join(FipFacets, FipFacets.fip_id == FipDeclaration.fip_id)
    if status != "any":
        stmt = stmt.where(FipDeclaration.status == status)
    if catalogued == "only":
        stmt = stmt.where(FipDeclaration.fer_id.isnot(None))
    elif catalogued == "exclude":
        stmt = stmt.where(FipDeclaration.fer_id.is_(None))
    group_cols = [group_col, FipDeclaration.fer_key, FipDeclaration.fer_id, FipDeclaration.status]
    if fer_type_is_grouped:
        group_cols.append(FipDeclaration.fer_type)
    stmt = stmt.group_by(*group_cols).order_by(
        func.count(func.distinct(FipDeclaration.fip_id)).desc(), FipDeclaration.fer_key.asc()
    )

    all_rows = list(db.execute(stmt).all())
    total = len(all_rows)
    return all_rows[offset : offset + limit], total


def adoption_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    group_by: str = "fer",
    status: str = "current",
    catalogued: str = "any",
    limit: int = 50,
    offset: int = 0,
    pop: ResolvedPopulation | None = None,
) -> dict[str, Any]:
    if group_by not in ADOPTION_GROUP_BYS:
        raise DashboardError(400, {"detail": "invalid_group_by"})
    limit = min(max(limit, 1), 200)
    if pop is None:
        pop = _prepare_population(db, spec, viewer)
    degraded = _check_staleness(pop)

    params_key = f"{group_by}{status}{catalogued}{limit}{offset}"
    if not pop.fip_ids:
        data = {"rows": [], "total": 0, "truncated": False}
        return _envelope(
            "adoption", spec, pop, data, viewer=viewer, degraded=False, params_key=params_key
        )

    if degraded:
        rows, total = _adoption_degraded_rows(db, pop, group_by, status, catalogued, limit, offset)
    else:
        rows, total = _adoption_aggregate_rows(
            db,
            pop.fip_ids,
            group_by=group_by,
            status=status,
            catalogued=catalogued,
            limit=limit,
            offset=offset,
        )

    # spec §3.2: exactly two extra, bounded statements -- never conditional
    # on whether *this* page happens to contain a catalogued FER or a
    # free-text one, so the statement count stays the same integer at every
    # population size (AC-16/§8.2's N+1 detector).
    fer_ids = [r.fer_id for r in rows if getattr(r, "fer_id", None)]
    fer_labels = {f.id: f for f in db.query(Fer).filter(Fer.id.in_(fer_ids)).all()}

    text_keys = [r.fer_key for r in rows if not getattr(r, "fer_id", None)]
    first_free_text = _first_seen_free_text(db, pop.fip_ids, text_keys)

    out_rows = []
    for r in rows:
        fer_row = fer_labels.get(getattr(r, "fer_id", None))
        if fer_row is not None:
            label = fer_row.label.get("en") or next(iter(fer_row.label.values()), None)
        else:
            label = first_free_text.get(r.fer_key)
        out_rows.append(
            {
                "ferKey": r.fer_key,
                "ferId": r.fer_id,
                "label": label,
                "ferType": r.fer_type,
                "status": r.status,
                "fips": r.fips,
                "declarations": r.declarations,
                "share": (r.fips / pop.count) if pop.count else 0.0,
                "groupKey": r.group_key,
            }
        )

    data = {"rows": out_rows, "total": total, "truncated": total > offset + len(rows)}
    return _envelope(
        "adoption", spec, pop, data, viewer=viewer, degraded=degraded, params_key=params_key
    )


def _adoption_degraded_rows(
    db: Session,
    pop: ResolvedPopulation,
    group_by: str,
    status: str,
    catalogued: str,
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    from types import SimpleNamespace

    km_content = _km_content_cache(db)
    fips_by_id = {f.id: f for f in db.query(Fip).filter(Fip.id.in_(pop.fip_ids)).all()}
    facets_by_id = {
        f.fip_id: f for f in db.query(FipFacets).filter(FipFacets.fip_id.in_(pop.fip_ids)).all()
    }
    agg: dict[tuple, dict[str, Any]] = {}
    for fip_id in pop.fip_ids:
        fip = fips_by_id.get(fip_id)
        if fip is None:
            continue
        content = km_content(fip.questionnaire_id, fip.questionnaire_version)
        projected = project_answers(content, fip.answers)
        seen_fips: set[tuple] = set()
        for decl in projected.declarations:
            if status != "any" and decl.status != status:
                continue
            if catalogued == "only" and not decl.fer_id:
                continue
            if catalogued == "exclude" and decl.fer_id:
                continue
            if group_by == "ferType":
                group_key = decl.fer_type
            elif group_by == "question":
                group_key = decl.question_id
            elif group_by == "area":
                group_key = facets_by_id[fip_id].area_key if fip_id in facets_by_id else None
            else:
                group_key = decl.fer_key
            key = (group_key, decl.fer_key, decl.fer_id, decl.fer_type, decl.status)
            bucket = agg.setdefault(
                key,
                {
                    "group_key": group_key,
                    "fer_key": decl.fer_key,
                    "fer_id": decl.fer_id,
                    "fer_type": decl.fer_type,
                    "status": decl.status,
                    "fips": 0,
                    "declarations": 0,
                },
            )
            bucket["declarations"] += 1
            if key not in seen_fips:
                bucket["fips"] += 1
                seen_fips.add(key)
    rows = sorted(agg.values(), key=lambda b: (-b["fips"], b["fer_key"]))
    total = len(rows)
    page = [SimpleNamespace(**r) for r in rows[offset : offset + limit]]
    return page, total


# ---------------------------------------------------------------------------
# §3.4 Gaps and coherence
# ---------------------------------------------------------------------------


def _gaps_aggregate_rows(db: Session, fip_ids: list[str]) -> list[Any]:
    from sqlalchemy import case

    stmt = (
        select(
            FipCell.question_id,
            FipCell.question_index,
            FipCell.sub_principle,
            FipCell.principle_group,
            FipCell.fer_type,
            func.count().label("fips"),
            func.sum(case((FipCell.cell_state == "unanswered", 1), else_=0)).label("unanswered"),
            func.sum(case((FipCell.cell_state == "none", 1), else_=0)).label("none_only"),
            func.sum(case((FipCell.cell_state == "not-applicable", 1), else_=0)).label(
                "not_applicable"
            ),
            func.sum(case((FipCell.cell_state == "planned", 1), else_=0)).label("planned_only"),
            func.sum(FipCell.coherence_flags).label("coherence_flags"),
            func.sum(case((FipCell.type_mismatch_ack.is_(True), 1), else_=0)).label(
                "type_mismatches"
            ),
        )
        .where(FipCell.fip_id.in_(fip_ids))
        .group_by(
            FipCell.question_id,
            FipCell.question_index,
            FipCell.sub_principle,
            FipCell.principle_group,
            FipCell.fer_type,
        )
    )
    return list(db.execute(stmt).all())


def _gaps_degraded_rows(db: Session, pop: ResolvedPopulation) -> list[Any]:
    from types import SimpleNamespace

    km_content = _km_content_cache(db)
    fips_by_id = {f.id: f for f in db.query(Fip).filter(Fip.id.in_(pop.fip_ids)).all()}
    agg: dict[str, dict[str, Any]] = {}
    for fip_id in pop.fip_ids:
        fip = fips_by_id.get(fip_id)
        if fip is None:
            continue
        content = km_content(fip.questionnaire_id, fip.questionnaire_version)
        projected = project_answers(content, fip.answers)
        for cell in projected.cells:
            bucket = agg.setdefault(
                cell.question_id,
                {
                    "question_id": cell.question_id,
                    "question_index": cell.question_index,
                    "sub_principle": cell.sub_principle,
                    "principle_group": cell.principle_group,
                    "fer_type": cell.fer_type,
                    "fips": 0,
                    "unanswered": 0,
                    "none_only": 0,
                    "not_applicable": 0,
                    "planned_only": 0,
                    "coherence_flags": 0,
                    "type_mismatches": 0,
                },
            )
            bucket["fips"] += 1
            if cell.cell_state == "unanswered":
                bucket["unanswered"] += 1
            elif cell.cell_state == "none":
                bucket["none_only"] += 1
            elif cell.cell_state == "not-applicable":
                bucket["not_applicable"] += 1
            elif cell.cell_state == "planned":
                bucket["planned_only"] += 1
    return [SimpleNamespace(**b) for b in agg.values()]


def gaps_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    min_share: float = 0.0,
    limit: int = 500,
    offset: int = 0,
    pop: ResolvedPopulation | None = None,
) -> dict[str, Any]:
    limit = min(max(limit, 1), 500)
    if pop is None:
        pop = _prepare_population(db, spec, viewer)
    degraded = _check_staleness(pop)
    params_key = f"{min_share}{limit}{offset}"

    if not pop.fip_ids:
        return _envelope(
            "gaps",
            spec,
            pop,
            {"rows": [], "total": 0},
            viewer=viewer,
            degraded=False,
            params_key=params_key,
        )

    rows = _gaps_degraded_rows(db, pop) if degraded else _gaps_aggregate_rows(db, pop.fip_ids)
    out_rows = []
    for r in rows:
        share = (r.unanswered + r.none_only) / r.fips if r.fips else 0.0
        if share < min_share:
            continue
        out_rows.append(
            {
                "questionId": r.question_id,
                "questionIndex": r.question_index,
                "subPrinciple": r.sub_principle,
                "principleGroup": r.principle_group,
                "ferType": r.fer_type,
                "fips": r.fips,
                "unanswered": r.unanswered,
                "noneOnly": r.none_only,
                "notApplicable": r.not_applicable,
                "plannedOnly": r.planned_only,
                "coherenceFlags": r.coherence_flags or 0,
                "typeMismatches": r.type_mismatches or 0,
                "share": share,
            }
        )
    out_rows.sort(key=lambda r: r["questionIndex"])
    total = len(out_rows)
    page = out_rows[offset : offset + limit]
    data = {"rows": page, "total": total}
    return _envelope(
        "gaps", spec, pop, data, viewer=viewer, degraded=degraded, params_key=params_key
    )


# ---------------------------------------------------------------------------
# §3.5 Evolution
# ---------------------------------------------------------------------------


def _evolution_planned_rows(
    db: Session, fip_ids: list[str], limit: int, offset: int
) -> tuple[list[Any], int]:
    stmt = (
        select(
            FipDeclaration.sub_principle,
            FipDeclaration.question_id,
            FipDeclaration.status,
            FipDeclaration.fer_key,
            FipDeclaration.successor_fer_key,
            func.count(func.distinct(FipDeclaration.fip_id)).label("fips"),
        )
        .where(FipDeclaration.fip_id.in_(fip_ids), FipDeclaration.status.in_(PLANNED_STATUSES))
        .group_by(
            FipDeclaration.sub_principle,
            FipDeclaration.question_id,
            FipDeclaration.status,
            FipDeclaration.fer_key,
            FipDeclaration.successor_fer_key,
        )
        .order_by(func.count(func.distinct(FipDeclaration.fip_id)).desc())
    )
    all_rows = list(db.execute(stmt).all())
    return all_rows[offset : offset + limit], len(all_rows)


def _evolution_migration_rows(db: Session, fip_ids: list[str]) -> list[Any]:
    stmt = (
        select(
            FipFacets.questionnaire_id,
            FipFacets.questionnaire_version,
            FipFacets.migrated_from_id,
            FipFacets.migrated_from_version,
            func.count().label("fips"),
        )
        .where(FipFacets.fip_id.in_(fip_ids), FipFacets.migrated_from_id.isnot(None))
        .group_by(
            FipFacets.questionnaire_id,
            FipFacets.questionnaire_version,
            FipFacets.migrated_from_id,
            FipFacets.migrated_from_version,
        )
    )
    return list(db.execute(stmt).all())


def _evolution_degraded(
    db: Session, pop: ResolvedPopulation, limit: int, offset: int
) -> tuple[list[Any], int, list[Any]]:
    from types import SimpleNamespace

    km_content = _km_content_cache(db)
    fips_by_id = {f.id: f for f in db.query(Fip).filter(Fip.id.in_(pop.fip_ids)).all()}
    planned: dict[tuple, dict[str, Any]] = {}
    migrations: dict[tuple, dict[str, Any]] = {}
    for fip_id in pop.fip_ids:
        fip = fips_by_id.get(fip_id)
        if fip is None:
            continue
        content = km_content(fip.questionnaire_id, fip.questionnaire_version)
        projected = project_answers(content, fip.answers)
        seen: set[tuple] = set()
        for decl in projected.declarations:
            if decl.status not in PLANNED_STATUSES:
                continue
            key = (
                decl.sub_principle,
                decl.question_id,
                decl.status,
                decl.fer_key,
                decl.successor_fer_key,
            )
            bucket = planned.setdefault(
                key,
                {
                    "sub_principle": decl.sub_principle,
                    "question_id": decl.question_id,
                    "status": decl.status,
                    "fer_key": decl.fer_key,
                    "successor_fer_key": decl.successor_fer_key,
                    "fips": 0,
                },
            )
            if key not in seen:
                bucket["fips"] += 1
                seen.add(key)
        migrated_from = fip.migrated_from or {}
        if migrated_from.get("id"):
            mkey = (
                fip.questionnaire_id,
                fip.questionnaire_version,
                migrated_from.get("id"),
                migrated_from.get("version"),
            )
            mbucket = migrations.setdefault(
                mkey,
                {
                    "questionnaire_id": fip.questionnaire_id,
                    "questionnaire_version": fip.questionnaire_version,
                    "migrated_from_id": migrated_from.get("id"),
                    "migrated_from_version": migrated_from.get("version"),
                    "fips": 0,
                },
            )
            mbucket["fips"] += 1
    planned_rows = sorted(planned.values(), key=lambda b: -b["fips"])
    total = len(planned_rows)
    page = [SimpleNamespace(**r) for r in planned_rows[offset : offset + limit]]
    migration_rows = [SimpleNamespace(**r) for r in migrations.values()]
    return page, total, migration_rows


def evolution_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    group_by: str = "subPrinciple",
    limit: int = 100,
    offset: int = 0,
    pop: ResolvedPopulation | None = None,
) -> dict[str, Any]:
    limit = min(max(limit, 1), 500)
    if pop is None:
        pop = _prepare_population(db, spec, viewer)
    degraded = _check_staleness(pop)
    params_key = f"{group_by}{limit}{offset}"

    if not pop.fip_ids:
        data = {
            "planned": {"rows": [], "total": 0, "truncated": False},
            "migrations": {"rows": [], "total": 0, "truncated": False},
        }
        return _envelope(
            "evolution", spec, pop, data, viewer=viewer, degraded=False, params_key=params_key
        )

    if degraded:
        planned_rows, total, migration_rows = _evolution_degraded(db, pop, limit, offset)
    else:
        planned_rows, total = _evolution_planned_rows(db, pop.fip_ids, limit, offset)
        migration_rows = _evolution_migration_rows(db, pop.fip_ids)

    planned_out = [
        {
            "subPrinciple": r.sub_principle,
            "questionId": r.question_id,
            "status": r.status,
            "ferKey": r.fer_key,
            "successorFerKey": r.successor_fer_key,
            "fips": r.fips,
        }
        for r in planned_rows
    ]
    migrations_out = [
        {
            "questionnaireId": r.questionnaire_id,
            "questionnaireVersion": r.questionnaire_version,
            "migratedFromId": r.migrated_from_id,
            "migratedFromVersion": r.migrated_from_version,
            "fips": r.fips,
        }
        for r in migration_rows
    ]
    migrations_out.sort(key=lambda r: -r["fips"])
    migrations_truncated = len(migrations_out) > 500
    migrations_out = migrations_out[:500]

    data = {
        "planned": {
            "rows": planned_out,
            "total": total,
            "truncated": total > offset + len(planned_out),
        },
        "migrations": {
            "rows": migrations_out,
            "total": len(migrations_out),
            "truncated": migrations_truncated,
        },
    }
    return _envelope(
        "evolution", spec, pop, data, viewer=viewer, degraded=degraded, params_key=params_key
    )
