"""spec 13-fip-dashboard.md §3.3/§4: `…/pair`, `…/neighbours`, `…/clusters`,
`…/map`, plus the typeahead endpoint of Builder brief B item 6. Candidate
generation (§4.3/§4.4) lives here; the exact score itself is always
`fipm.similarity.score_pair`, recomputed over stored declarations -- never
approximated by MinHash/LSH (§4.2's central invariant, AC-24).

Response shapes are transcribed field-for-field from
`frontend/src/types/dashboard.ts` (the authoritative wire contract for these
four endpoints, per the brief) -- see this module's functions for the exact
dict shapes returned as `data`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import (
    Integer,
    String,
    and_,
    case,
    exists,
    func,
    literal,
    select,
    tuple_,
    union_all,
)
from sqlalchemy.orm import Session, aliased

from fipm import similarity
from fipm.authz import can_read
from fipm.config import get_settings
from fipm.dashboard import DashboardError
from fipm.dashboard.populations import (
    ResolvedPopulation,
    auth_scope_for,
    canonicalise_spec,
    check_k_anonymity,
    current_projection_epoch,
    population_hash,
    resolve_population,
)
from fipm.dashboard.snapshots import _aware, build_etag
from fipm.dashboard.snapshots import params_hash as _params_hash
from fipm.models import (
    Fip,
    FipCell,
    FipDeclaration,
    FipFacets,
    FipSignatureBand,
    LshHotBucket,
    NetworkFip,
    User,
)

WEIGHTINGS = ("principle", "question", "letter")
STATUSES_PARAM = ("current", "currentPlanned")


def _is_network_id(fip_id: str) -> bool:
    return fip_id.startswith("net:")


def _not_found() -> DashboardError:
    return DashboardError(404, {"detail": "not_found"})


def _readable(db: Session, viewer: User | None, fip_id: str) -> bool:
    """A FIP the viewer may fetch by id (spec §2.4's `readable_individually`
    -- the *same* rule every named-FIP field in this module is filtered
    through, so no response ever names an unreadable FIP). Network shadow
    rows are always readable (public nanopublications by construction,
    §5.4)."""
    if _is_network_id(fip_id):
        return db.get(NetworkFip, fip_id) is not None
    fip = db.get(Fip, fip_id)
    if fip is None:
        return False
    return can_read(fip.owner_id, fip.visibility, viewer)


def _entity_updated_at(db: Session, fip_id: str) -> datetime | None:
    """Freshness stamp for one FIP or network shadow row -- used by `pair`'s
    ETag (§4/finding #4), which has no `ResolvedPopulation` of its own to
    read `max_updated_at` from.

    Reads via `db.get()`, which serves whatever is already in the identity
    map: a value set in Python earlier this session (tz-aware) if the
    instance hasn't been expired, or a freshly-reloaded one otherwise --
    and SQLite round-trips `DateTime(timezone=True)` as naive on reload
    (the same convention `fipm.dashboard.snapshots._aware` exists for).
    Normalised here, at the point this module reads the timestamp, so every
    caller downstream (in particular `pair_view`'s `max()` over both sides)
    always compares two aware values."""
    if _is_network_id(fip_id):
        n = db.get(NetworkFip, fip_id)
        return _aware(n.fetched_at) if n is not None else None
    f = db.get(Fip, fip_id)
    return _aware(f.updated_at) if f is not None else None


# ---------------------------------------------------------------------------
# One combined statement: cells + (all-status) declarations + label/areaKey
# metadata, for a bounded set of fip ids. Used by pair/neighbours/clusters/
# map alike so each stays at exactly the statement count its AC names.
# ---------------------------------------------------------------------------


@dataclass
class FipData:
    cells: list[Any] = field(default_factory=list)
    declarations: list[Any] = field(default_factory=list)
    label: str | None = None
    area_key: str | None = None


def fetch_fip_data(db: Session, fip_ids: list[str]) -> dict[str, FipData]:
    """One statement (a `UNION ALL` of four branches, still one
    `db.execute()` call): every `fip_cells` row, every `fip_declarations`
    row (any status -- `statuses=currentPlanned` needs `planned*` rows
    too, so this never pre-filters to `current`), and a label/`areaKey`
    lookup that works for both a local `Fip` and a `NetworkFip` shadow row.
    Bounded by `len(fip_ids)` (≤ candidate_cap + 1 for neighbours,
    ≤ pair_cap*2 for clusters/map)."""
    if not fip_ids:
        return {}

    cell_stmt = select(
        literal("cell").label("kind"),
        FipCell.fip_id.label("fip_id"),
        FipCell.question_id.label("a"),
        FipCell.sub_principle.label("b"),
        FipCell.not_applicable.label("c"),
        literal(None, type_=String).label("d"),
    ).where(FipCell.fip_id.in_(fip_ids))

    decl_stmt = select(
        literal("decl").label("kind"),
        FipDeclaration.fip_id.label("fip_id"),
        FipDeclaration.question_id.label("a"),
        FipDeclaration.fer_key.label("b"),
        literal(None, type_=Integer).label("c"),
        FipDeclaration.status.label("d"),
    ).where(FipDeclaration.fip_id.in_(fip_ids))

    local_facets = aliased(FipFacets)
    meta_local_stmt = (
        select(
            literal("meta").label("kind"),
            Fip.id.label("fip_id"),
            Fip.title.label("a"),
            local_facets.area_key.label("b"),
            literal(None, type_=Integer).label("c"),
            literal(None, type_=String).label("d"),
        )
        .outerjoin(
            local_facets, and_(local_facets.fip_id == Fip.id, local_facets.source == "local")
        )
        .where(Fip.id.in_(fip_ids))
    )

    net_facets = aliased(FipFacets)
    meta_network_stmt = (
        select(
            literal("meta").label("kind"),
            NetworkFip.fip_id.label("fip_id"),
            NetworkFip.label.label("a"),
            net_facets.area_key.label("b"),
            literal(None, type_=Integer).label("c"),
            literal(None, type_=String).label("d"),
        )
        .outerjoin(
            net_facets, and_(net_facets.fip_id == NetworkFip.fip_id, net_facets.source == "network")
        )
        .where(NetworkFip.fip_id.in_(fip_ids))
    )

    combined = union_all(cell_stmt, decl_stmt, meta_local_stmt, meta_network_stmt)

    out: dict[str, FipData] = defaultdict(FipData)
    for row in db.execute(combined):
        entry = out[row.fip_id]
        if row.kind == "cell":
            entry.cells.append(
                SimpleNamespace(question_id=row.a, sub_principle=row.b, not_applicable=bool(row.c))
            )
        elif row.kind == "decl":
            entry.declarations.append(
                SimpleNamespace(question_id=row.a, fer_key=row.b, status=row.d)
            )
        elif row.kind == "meta" and entry.label is None:
            entry.label = row.a
            entry.area_key = row.b
    for fip_id in fip_ids:
        entry = out.setdefault(fip_id, FipData())
        if entry.label is None:
            entry.label = fip_id
    return dict(out)


def _score(a: FipData, b: FipData, *, statuses: str) -> similarity.PairScore:
    return similarity.score_pair(
        a.cells, a.declarations, b.cells, b.declarations, statuses=statuses
    )


# ---------------------------------------------------------------------------
# §3.3 pair -- always live, two FIPs, ~100 rows (§5.2).
# ---------------------------------------------------------------------------


def _minimal_envelope(
    view: str,
    key: str,
    fip_count: int,
    data: dict[str, Any],
    *,
    scope: str = "n/a",
    params: dict[str, Any] | None = None,
    epoch: int = 0,
    max_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Confirmed finding #4: the ETag used to be `W/"<view>-<key>-<date>"`,
    varying only per calendar day, with every caller passing a literal
    `'x'` for `scope`. That let `Cache-Control: private, must-revalidate`
    304 a viewer back a body that predates a mid-session declaration, and
    let two different signed-in viewers collide on one ETag. Now built with
    the *same* `snapshots.build_etag` formula every other view uses --
    keyed on the real `scope`, the actual `params`, the current
    `projection_epoch`, and the source data's own freshness stamp
    (`max_updated_at`) -- so a change to the underlying data changes the
    ETag on the very next request, regardless of what day it is."""
    now = datetime.now(UTC)
    etag = build_etag(view, key, _params_hash(params or {}), epoch, max_updated_at, fip_count)
    return {
        "population": {"hash": key, "authScope": scope, "fipCount": fip_count, "label": None},
        "tier": "live",
        "computedAt": now.isoformat().replace("+00:00", "Z"),
        "degraded": False,
        "degradedReason": None,
        "staleFips": None,
        "etag": etag,
        "data": data,
    }


def pair_view(
    db: Session,
    viewer: User | None,
    *,
    a: str,
    b: str,
    weighting: str = "principle",
    statuses: str = "current",
) -> dict[str, Any]:
    if weighting not in WEIGHTINGS:
        raise DashboardError(400, {"detail": "invalid_population"})
    if not _readable(db, viewer, a) or not _readable(db, viewer, b):
        raise _not_found()

    fip_data = fetch_fip_data(db, [a, b])
    score = _score(fip_data[a], fip_data[b], statuses=statuses)

    data = {
        "a": {"id": a, "label": fip_data[a].label or a},
        "b": {"id": b, "label": fip_data[b].label or b},
        "overall": score.overall[weighting],
        "weighting": weighting,
        "statuses": statuses,
        "perPrinciple": score.per_principle,
        "perQuestion": [
            {"questionId": qs.question_id, "jaccard": qs.jaccard, "included": qs.included}
            for qs in score.per_question
        ],
    }
    max_updated_at = max(
        (t for t in (_entity_updated_at(db, a), _entity_updated_at(db, b)) if t is not None),
        default=None,
    )
    return _minimal_envelope(
        "pair",
        f"{a[:8]}-{b[:8]}",
        2,
        data,
        params={"weighting": weighting, "statuses": statuses},
        epoch=current_projection_epoch(db),
        max_updated_at=max_updated_at,
    )


# ---------------------------------------------------------------------------
# §4.3 neighbours -- always live, population-size-independent (§5.2).
# ---------------------------------------------------------------------------


def _selected_keys_for_neighbours(
    subject_pairs: list[tuple[str, str, int]], population_count: int, settings
) -> tuple[list[tuple[str, str]], list[str]]:
    """spec §4.3 step 2's key-selection rule: order by `df` ascending
    (rarest first), skip a key held by more than `DF_SKIP_SHARE` of the
    population *unless* fewer than `DF_MIN_KEYS` keys would then survive
    (take the rarest `DF_MIN_KEYS` regardless). Returns `(selected,
    skipped_popular_keys)`; `subject_pairs` is `[(question_id, fer_key,
    df)]`, already fetched in ascending-`df` order."""
    if population_count <= 0:
        return [], []
    skip_share = settings.dashboard_df_skip_share
    min_keys = settings.dashboard_df_min_keys

    kept: list[tuple[str, str, int]] = []
    skipped: list[tuple[str, str, int]] = []
    for question_id, fer_key, df in subject_pairs:
        share = df / population_count
        if share > skip_share:
            skipped.append((question_id, fer_key, df))
        else:
            kept.append((question_id, fer_key, df))

    if len(kept) < min_keys:
        # Fall back to the rarest `min_keys` overall, popularity guard or not.
        all_sorted = sorted(subject_pairs, key=lambda t: t[2])
        kept = all_sorted[:min_keys]
        used_keys = {(q, k) for q, k, _ in kept}
        skipped = [t for t in subject_pairs if (t[0], t[1]) not in used_keys]

    return [(q, k) for q, k, _ in kept], [k for _, k, _ in skipped]


def neighbours_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    fip_id: str,
    weighting: str = "principle",
    statuses: str = "current",
    limit: int = 20,
    min_similarity: float = 0.0,
    debug: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """spec §4.3, in exactly 4 statements total (AC, scale test): population
    resolution, step 1 (the subject's own keys + df), step 2 (candidate
    generation), step 3 (`fetch_fip_data` for the candidates + subject)."""
    if weighting not in WEIGHTINGS:
        raise DashboardError(400, {"detail": "invalid_population"})
    settings = get_settings()
    limit = min(max(limit, 1), 100)

    pop = resolve_population(db, spec, viewer)
    check_k_anonymity(pop)
    fip_ids = pop.fip_ids
    # `pop.members` already carries `readable_individually` per FIP (one
    # statement, already paid for by `resolve_population` above) -- every
    # candidate this function will ever consider is a population member,
    # so this dict is the readability check for the rest of the function,
    # never a per-candidate `_readable()`/db.get() call (which would be an
    # N+1 exactly like the ones AC-5's population-independent cost bound
    # forbids).
    readable_by_id = {m.fip_id: m.readable_individually for m in pop.members}
    if fip_id not in fip_ids or not readable_by_id.get(fip_id, False):
        raise _not_found()

    # Step 1: the subject's own (question_id, fer_key) pairs and their df,
    # ordered rarest-first.
    from fipm.models import FerKeyDf

    step1_stmt = (
        select(
            FipDeclaration.question_id,
            FipDeclaration.fer_key,
            func.coalesce(FerKeyDf.df_all, 0).label("df"),
        )
        .outerjoin(
            FerKeyDf,
            and_(
                FerKeyDf.question_id == FipDeclaration.question_id,
                FerKeyDf.fer_key == FipDeclaration.fer_key,
            ),
        )
        .where(FipDeclaration.fip_id == fip_id, FipDeclaration.status == "current")
        .order_by(func.coalesce(FerKeyDf.df_all, 0).asc())
    )
    subject_pairs = [(r.question_id, r.fer_key, r.df) for r in db.execute(step1_stmt)]

    selected, skipped_popular = _selected_keys_for_neighbours(subject_pairs, pop.count, settings)

    budget = settings.dashboard_posting_budget
    posting_cap = settings.dashboard_posting_cap
    keys_used: list[tuple[str, str]] = []
    posting_truncated = False
    remaining_budget = budget
    for question_id, fer_key in selected:
        if remaining_budget <= 0:
            break
        keys_used.append((question_id, fer_key))
        remaining_budget -= posting_cap
    candidate_budget_exhausted = len(keys_used) < len(selected)

    # Step 2: candidate generation, one statement -- a UNION ALL of one
    # per-key subselect (each capped at `posting_cap`, `fip_id ASC`, per
    # spec §4.3's deterministic truncation), grouped/counted in Python
    # (bounded by `posting_budget` rows, so cheap either way).
    candidates: Counter[str] = Counter()
    posting_rows_scanned = 0
    if keys_used:
        branches = []
        for question_id, fer_key in keys_used:
            # SQLite (unlike Postgres) forbids ORDER BY/LIMIT on an
            # individual member of a compound SELECT -- only the whole
            # compound may carry one. Each per-key posting list is instead
            # built as its own capped subquery, wrapped by a plain outer
            # SELECT with no ORDER BY/LIMIT of its own, so the UNION ALL
            # itself stays a single, portable statement.
            capped = (
                select(FipDeclaration.fip_id)
                .where(
                    FipDeclaration.question_id == question_id,
                    FipDeclaration.fer_key == fer_key,
                    FipDeclaration.status == "current",
                    FipDeclaration.fip_id != fip_id,
                    FipDeclaration.fip_id.in_(fip_ids),
                )
                .order_by(FipDeclaration.fip_id.asc())
                .limit(posting_cap)
                .subquery()
            )
            branches.append(select(capped.c.fip_id))
        step2_stmt = union_all(*branches) if len(branches) > 1 else branches[0]
        for row in db.execute(step2_stmt):
            candidates[row[0]] += 1
            posting_rows_scanned += 1
        posting_truncated = any(
            df > posting_cap for q, k, df in subject_pairs if (q, k) in set(keys_used)
        )

    candidate_cap = settings.dashboard_candidate_cap
    ranked = sorted(candidates.items(), key=lambda kv: (-kv[1], kv[0]))[:candidate_cap]
    candidate_ids = [c for c, _ in ranked]

    # Step 3: one statement, cells + declarations + labels for the
    # candidates plus the subject.
    fip_data = fetch_fip_data(db, [fip_id, *candidate_ids])
    subject_data = fip_data.get(fip_id, FipData())

    rows = []
    for candidate_id, _shared_keys_count in ranked:
        candidate_data = fip_data.get(candidate_id, FipData())
        if not readable_by_id.get(candidate_id, False):
            continue
        score = _score(subject_data, candidate_data, statuses=statuses)
        overall = score.overall[weighting]
        if overall < min_similarity:
            continue
        top_shared = [
            {"questionId": qid, "ferKey": fer_key, "label": fer_key}
            for qid, fer_key in score.shared_pairs[:5]
        ]
        rows.append(
            {
                "fipId": candidate_id,
                "label": candidate_data.label or candidate_id,
                "areaKey": candidate_data.area_key,
                "similarity": overall,
                "sharedKeys": score.shared_keys,
                "perPrinciple": score.per_principle,
                "topShared": top_shared,
            }
        )
    rows.sort(key=lambda r: (-r["similarity"], r["fipId"]))
    rows = rows[:limit]

    if debug is not None:
        debug["posting_rows_scanned"] = posting_rows_scanned
        debug["keys_used"] = len(keys_used)
        debug["candidates_scored"] = len(ranked)

    data = {
        "fip": {"id": fip_id, "label": subject_data.label or fip_id},
        "neighbours": rows,
        "weighting": weighting,
        "statuses": statuses,
        "candidateBudgetExhausted": candidate_budget_exhausted,
        "postingTruncated": posting_truncated,
        "skippedPopularKeys": skipped_popular,
        "keysUsed": len(keys_used),
        "candidatesScored": len(ranked),
    }
    scope = auth_scope_for(spec, viewer)
    max_updated_at = max((m.updated_at for m in pop.members), default=None)
    return _minimal_envelope(
        "neighbours",
        f"{fip_id[:8]}-{population_hash(canonicalise_spec(spec), scope)[:8]}",
        pop.count,
        data,
        scope=scope,
        params={
            "fip": fip_id,
            "weighting": weighting,
            "statuses": statuses,
            "limit": limit,
            "minSimilarity": min_similarity,
        },
        epoch=pop.current_epoch,
        max_updated_at=max_updated_at,
    )


# ---------------------------------------------------------------------------
# §4.4 clusters / map -- exact all-pairs at or below EXACT_PAIRS_MAX_FIPS,
# LSH candidates above it; never O(n^2) at request time.
# ---------------------------------------------------------------------------


def _scoped_hot_groups(
    db: Session,
    fip_ids: list[str],
    hot_bucket_rows: list[Any],
) -> list[tuple[str, int]]:
    """Confirmed finding #7: `lsh_hot_buckets.member_count` is a **global**
    count over the whole `fip_signature_bands` table (maintained by the
    refresh job, spec §4.4), unrelated to the requested population -- a
    100-FIP population could report a bucket `size` in the tens of
    thousands, counting FIPs outside the population and ones the viewer
    cannot read. Rescoped here to "how many of *this bucket's* members are
    in *this* population", via one extra grouped query keyed on the exact
    `(band_index, band_hash)` pairs already selected (dedup by
    representative keeps one row per group; all its `member_count` rows
    share the same underlying member set per the dedup note above, so any
    one `(band_index, band_hash)` for a given representative identifies the
    bucket). A representative with no other population member scores out at
    1 and is dropped -- a hot "group" of one is not a group."""
    if not hot_bucket_rows:
        return []
    keys_by_representative: dict[str, tuple[int, int]] = {}
    for row in hot_bucket_rows:
        keys_by_representative.setdefault(
            row.representative_fip_id, (row.band_index, row.band_hash)
        )
    keys = list(keys_by_representative.values())
    stmt = (
        select(
            FipSignatureBand.band_index,
            FipSignatureBand.band_hash,
            func.count().label("n"),
        )
        .where(
            tuple_(FipSignatureBand.band_index, FipSignatureBand.band_hash).in_(keys),
            FipSignatureBand.fip_id.in_(fip_ids),
        )
        .group_by(FipSignatureBand.band_index, FipSignatureBand.band_hash)
    )
    scoped_counts = {(r.band_index, r.band_hash): r.n for r in db.execute(stmt)}
    out: list[tuple[str, int]] = []
    for representative_id, key in keys_by_representative.items():
        n = scoped_counts.get(key, 0)
        if n >= 2:
            out.append((representative_id, n))
    return sorted(out)


def _lsh_candidate_pairs(db: Session, fip_ids: list[str], settings) -> list[tuple[str, str]]:
    """spec §4.4's band self-join.

    **Measured performance finding (scale test, N=2000, see `tests/scale/
    README.md`):** this statement alone took ~13-14s of `clusters`/`map`'s
    ~13-14s total wall time -- i.e. it is the *entire* cost, not the
    Python-side rescoring (~0.3s for the same run). Root-caused with
    `EXPLAIN QUERY PLAN`: SQLite's planner produces a good plan for the bare
    self-join (~0.2s, confirmed by hand) but a *much* worse one once both
    `a.fip_id`/`b.fip_id` carry a large `IN (...)` population filter --
    reproducible with a literal list, a bound-parameter list (what
    `.in_(fip_ids)` below compiles to), and a `IN (SELECT id FROM fips)`
    subquery alike (all ~13-14s at N=2000); only replacing the `IN` filter
    with an actual indexed `JOIN` against a materialised set of population
    ids (a temp table, in the reproduction) restored the ~0.2-0.3s plan.
    Not fixed here: a per-request temp table needs lifecycle/connection-
    affinity handling this module doesn't otherwise need, and brief B's
    time budget did not extend to it -- recorded for the architect/§7.4
    tuning pass rather than papered over. It does not affect correctness
    (AC-24's exact-score invariant and the LSH-vs-exact recall test both
    pass), only latency, and only above `EXACT_PAIRS_MAX_FIPS` where this
    path runs at all."""
    a = aliased(FipSignatureBand)
    b = aliased(FipSignatureBand)
    hot = exists(
        select(LshHotBucket.band_hash).where(
            LshHotBucket.band_index == a.band_index, LshHotBucket.band_hash == a.band_hash
        )
    )
    stmt = (
        select(a.fip_id.label("a_id"), b.fip_id.label("b_id"))
        .select_from(a)
        .join(
            b, and_(b.band_index == a.band_index, b.band_hash == a.band_hash, b.fip_id > a.fip_id)
        )
        .where(a.fip_id.in_(fip_ids), b.fip_id.in_(fip_ids), ~hot)
        .group_by(a.fip_id, b.fip_id)
        .limit(settings.dashboard_lsh_pair_cap)
    )
    return [(row.a_id, row.b_id) for row in db.execute(stmt)]


@dataclass
class PairEdge:
    a: str
    b: str
    score: float
    per_principle: dict[str, float]


def _score_edges(
    fip_data: dict[str, FipData],
    pairs: list[tuple[str, str]],
    *,
    weighting: str,
    statuses: str,
    min_sim: float,
) -> list[PairEdge]:
    edges: list[PairEdge] = []
    for a_id, b_id in pairs:
        a_data, b_data = fip_data.get(a_id), fip_data.get(b_id)
        if a_data is None or b_data is None:
            continue
        score = _score(a_data, b_data, statuses=statuses)
        overall = score.overall[weighting]
        if overall >= min_sim:
            edges.append(PairEdge(a_id, b_id, overall, score.per_principle))
    return edges


def _build_clusters(
    fip_ids: list[str],
    edges: list[PairEdge],
    fip_data: dict[str, FipData],
    hot_groups: list[tuple[str, int]],
    *,
    limit: int,
    readable: Any,
) -> list[dict[str, Any]]:
    components = similarity.cluster_edges(fip_ids, [(e.a, e.b) for e in edges])
    edge_score_by_pair = {(e.a, e.b): e.score for e in edges}
    edge_score_by_pair.update({(e.b, e.a): e.score for e in edges})

    clusters: list[dict[str, Any]] = []
    for _rep, members in components.items():
        if len(members) < 2:
            continue
        scores_by_member: dict[str, list[float]] = defaultdict(list)
        principle_sums: dict[str, list[float]] = defaultdict(list)
        for m in members:
            for other in members:
                if other == m:
                    continue
                s = edge_score_by_pair.get((m, other))
                if s is not None:
                    scores_by_member[m].append(s)
        mean_by_member = {m: (sum(v) / len(v) if v else 0.0) for m, v in scores_by_member.items()}
        readable_members = [m for m in members if readable(m)]
        if not readable_members:
            # §2.4: "no aggregate response ever names a FIP the viewer
            # cannot read individually" -- `id` and `representative` name a
            # specific FIP, and every member here is unreadable, so there is
            # no candidate that can fill either field without leaking one.
            # Decision (confirmed finding #1): drop the cluster entirely
            # rather than fabricate an id or expose an unreadable fipId.
            continue
        representative = max(readable_members, key=lambda m: (mean_by_member.get(m, 0.0), m))
        all_scores = [s for v in scores_by_member.values() for s in v]
        mean_similarity = sum(all_scores) / len(all_scores) if all_scores else 0.0
        for e in edges:
            if e.a in members and e.b in members:
                for p, v in e.per_principle.items():
                    principle_sums[p].append(v)
        principles = sorted(
            [p for p, vs in principle_sums.items() if vs and sum(vs) / len(vs) >= 0.5]
        )
        clusters.append(
            {
                "id": representative,
                # Round-3 review observation (lower priority, confirmed not
                # a leak): `len(members)` counts every connected-component
                # member, readable or not -- only `"members"` below (capped,
                # `readable_members`-only) and `"representative"` ever name
                # an individual FIP; `"size"` is a bare count, which is
                # exactly what §2.4's k-anonymity threshold bounds (a count
                # cannot re-identify anyone by itself). Left as-is.
                "size": len(members),
                "representative": {
                    "fipId": representative,
                    "label": fip_data.get(representative, FipData()).label or representative,
                },
                "meanSimilarity": mean_similarity,
                "principles": principles,
                "members": [
                    {"fipId": m, "label": fip_data.get(m, FipData()).label or m}
                    for m in sorted(readable_members)[:10]
                ],
            }
        )

    for representative_id, size in hot_groups:
        if not readable(representative_id):
            # Same rule as above: `lsh_hot_buckets` stores exactly one
            # representative globally (§4.4's refresh job), so if it isn't
            # readable by this viewer there is no other candidate id to
            # report `id`/`representative` as -- drop the hot-bucket entry
            # rather than name it.
            continue
        clusters.append(
            {
                "id": f"hot:{representative_id}",
                "size": size,
                "representative": {
                    "fipId": representative_id,
                    "label": fip_data.get(representative_id, FipData()).label or representative_id,
                },
                "meanSimilarity": 1.0,
                "principles": [],
                "members": [
                    {
                        "fipId": representative_id,
                        "label": fip_data.get(representative_id, FipData()).label
                        or representative_id,
                    }
                ],
            }
        )

    clusters.sort(key=lambda c: -c["size"])
    return clusters[:limit]


def clusters_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    min_similarity: float | None = None,
    limit: int = 50,
    pop: ResolvedPopulation | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    limit = min(max(limit, 1), 200)
    min_sim = min_similarity if min_similarity is not None else settings.dashboard_cluster_min_sim

    if pop is None:
        pop = resolve_population(db, spec, viewer)
        check_k_anonymity(pop)

    fip_ids = pop.fip_ids
    truncated = False
    if pop.count <= settings.dashboard_exact_pairs_max_fips:
        fip_data = fetch_fip_data(db, fip_ids)
        pairs = [
            (fip_ids[i], fip_ids[j])
            for i in range(len(fip_ids))
            for j in range(i + 1, len(fip_ids))
        ]
        edges = _score_edges(
            fip_data, pairs, weighting="principle", statuses="current", min_sim=min_sim
        )
        hot_groups: list[tuple[str, int]] = []
        hot_bucket_rows: list[Any] = []
    else:
        if pop.count > settings.dashboard_exact_pairs_max_fips * 2000:
            raise DashboardError(
                413,
                {
                    "detail": "similarity_population_too_large",
                    "cap": settings.dashboard_lsh_pair_cap,
                },
            )
        candidate_pairs = _lsh_candidate_pairs(db, fip_ids, settings)
        # Scoped to *this* population: a hot bucket is a global structure
        # (spec §4.4, maintained by the refresh job over the whole
        # `fip_signature_bands` table), but a cluster response must never
        # surface a group whose representative isn't even in the requested
        # population (D2-adjacent: naming a FIP outside the population is
        # exactly the kind of leak §2.4 forbids for every other view).
        #
        # Round-3 review observation (lower priority, confirmed not a
        # leak, left as-is): filtering by `representative_fip_id.in_
        # (fip_ids)` means a bucket whose *global* representative
        # (`MIN(fip_id)` over the whole table, per `refresh_hot_buckets`)
        # happens to sit outside this population is dropped entirely, even
        # when many of its other members are inside it -- an undercount of
        # `clusters`/`hotBuckets`, never an over-report or a leak (nothing
        # about a dropped bucket is ever named). Fixing this properly needs
        # a *population-scoped* representative (the smallest in-population
        # `fip_id` sharing that bucket's `(band_index, band_hash)`, chosen
        # per request) rather than reusing the global one computed once by
        # the refresh job -- a small change to `_scoped_hot_groups`' query
        # shape, but it would also change the `id`/`representative` this
        # view reports for such a bucket, which is a response-contract
        # change, not a same-behaviour bug fix -- left for the architect/
        # spec-13 tuning pass rather than made here.
        hot_bucket_rows = list(
            db.execute(
                select(
                    LshHotBucket.representative_fip_id,
                    LshHotBucket.member_count,
                    LshHotBucket.band_index,
                    LshHotBucket.band_hash,
                    # Round-3 fix (item C): fetched (no extra statement --
                    # already-selected columns just grow by one) so its max
                    # can be folded into this view's ETag freshness stamp
                    # below; see the comment at `max_updated_at` for why.
                    LshHotBucket.computed_at,
                ).where(LshHotBucket.representative_fip_id.in_(fip_ids))
            )
        )
        # Confirmed finding #7: `member_count` above is global, not scoped
        # to this population -- `_scoped_hot_groups` rescores it against
        # `fip_ids` (one extra grouped query) instead of trusting the
        # whole-table count.
        hot_groups = _scoped_hot_groups(db, fip_ids, hot_bucket_rows)
        rescored_ids = sorted(
            {i for pair in candidate_pairs for i in pair} | {g[0] for g in hot_groups}
        )
        fip_data = fetch_fip_data(db, rescored_ids)
        edges = _score_edges(
            fip_data, candidate_pairs, weighting="principle", statuses="current", min_sim=min_sim
        )
        truncated = len(candidate_pairs) >= settings.dashboard_lsh_pair_cap
        fip_ids = rescored_ids

    # `pop.members` already carries `readable_individually` (one statement,
    # already paid for above) -- every id `clusters_view` ever names came
    # from `fip_ids`/`rescored_ids`, both subsets of the population, so a
    # dict lookup replaces what would otherwise be a `_readable()` call per
    # cluster member (an N+1 this view's own statement-count budget cannot
    # afford).
    readable_by_id = {m.fip_id: m.readable_individually for m in pop.members}

    def _readable_fn(fip_id: str) -> bool:
        return readable_by_id.get(fip_id, False)

    clusters = _build_clusters(
        fip_ids, edges, fip_data, hot_groups, limit=limit, readable=_readable_fn
    )
    data = {"clusters": clusters, "truncated": truncated}

    scope = auth_scope_for(spec, viewer)
    phash = population_hash(canonicalise_spec(spec), scope)[:16]
    # Round-3 fix (item C): `refresh_hot_buckets()` rewrites `lsh_hot_
    # buckets` and changes this view's body (via `hot_groups` above)
    # without bumping `projection_epoch` or any population member's
    # `updated_at` -- the two inputs `build_etag` otherwise relies on for
    # freshness. `LshHotBucket.computed_at` is set to "now" on every
    # refresh (see `refresh_hot_buckets`), already fetched above at no
    # extra statement cost, so folding its max into the same freshness
    # stamp `build_etag` already hashes makes a refresh always change this
    # view's ETag for any population whose hot buckets it touches.
    max_updated_at = max(
        (m.updated_at for m in pop.members),
        default=None,
    )
    hot_bucket_max = max((r.computed_at for r in hot_bucket_rows), default=None)
    if hot_bucket_max is not None and (max_updated_at is None or hot_bucket_max > max_updated_at):
        max_updated_at = hot_bucket_max
    envelope_kwargs = {
        "scope": scope,
        "params": {"minSimilarity": min_sim, "limit": limit},
        "epoch": pop.current_epoch,
        "max_updated_at": max_updated_at,
    }
    if pop.count <= settings.dashboard_exact_pairs_max_fips:
        return _minimal_envelope("clusters", phash, pop.count, data, **envelope_kwargs)
    envelope = _minimal_envelope("clusters", phash, pop.count, data, **envelope_kwargs)
    envelope["tier"] = "live"
    return envelope


def map_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    buckets: int = 10,
    weighting: str = "principle",
    pop: ResolvedPopulation | None = None,
) -> dict[str, Any]:
    """spec §3.3/§4.4: histogram + `principle x bucket` grid + convergence
    (folded in, the matrix's own aggregate) + top clusters + hot buckets +
    scatter (only ≤ `FIPM_DASHBOARD_LIVE_MAX_FIPS_SCATTER`). Six
    statements total (scale test AC): population, convergence(a),
    convergence(b), candidate-pairs-or-all-pairs-fetch, rescore-fetch,
    hot-buckets lookup."""
    settings = get_settings()
    buckets = min(max(buckets, 1), 20)
    if weighting not in WEIGHTINGS:
        raise DashboardError(400, {"detail": "invalid_population"})

    if pop is None:
        pop = resolve_population(db, spec, viewer)
        check_k_anonymity(pop)
    if pop.count > settings.dashboard_exact_pairs_max_fips * 2000:
        raise DashboardError(
            413,
            {"detail": "similarity_population_too_large", "cap": settings.dashboard_lsh_pair_cap},
        )
    fip_ids = pop.fip_ids

    # Convergence, §3.3: two statements, folded into `map`. spec §11.3
    # amendment: `ConvergenceRow` also carries `notApplicableFips` (matching
    # `matrix.ts`'s `Convergence`) -- folded into the *same* first statement
    # as a second UNION ALL branch (fip_cells, not fip_declarations), so the
    # "two statements" budget for convergence is unchanged.
    conv_decl_part = (
        select(
            FipDeclaration.question_id.label("question_id"),
            literal("decl").label("kind"),
            func.count(func.distinct(FipDeclaration.fer_key)).label("val_a"),
            func.count(func.distinct(FipDeclaration.fip_id)).label("val_b"),
        )
        .where(FipDeclaration.fip_id.in_(fip_ids), FipDeclaration.status == "current")
        .group_by(FipDeclaration.question_id)
    )
    conv_na_part = (
        select(
            FipCell.question_id.label("question_id"),
            literal("na").label("kind"),
            literal(0, type_=Integer).label("val_a"),
            func.count().label("val_b"),
        )
        .where(FipCell.fip_id.in_(fip_ids), FipCell.not_applicable.is_(True))
        .group_by(FipCell.question_id)
    )
    conv_a_stmt = union_all(conv_decl_part, conv_na_part)
    conv_rows: dict[str, Any] = {}
    not_applicable_by_question: dict[str, int] = {}
    for row in db.execute(conv_a_stmt):
        if row.kind == "decl":
            conv_rows[row.question_id] = row
        else:
            not_applicable_by_question[row.question_id] = row.val_b

    conv_b_stmt = (
        select(
            FipDeclaration.question_id,
            FipDeclaration.fer_key,
            func.count().label("n"),
        )
        .where(FipDeclaration.fip_id.in_(fip_ids), FipDeclaration.status == "current")
        .group_by(FipDeclaration.question_id, FipDeclaration.fer_key)
        .order_by(FipDeclaration.question_id.asc(), func.count().desc())
    )
    top_by_question: dict[str, Any] = {}
    for row in db.execute(conv_b_stmt):
        if row.question_id not in top_by_question:
            top_by_question[row.question_id] = row

    convergence = []
    all_question_ids = set(conv_rows) | set(not_applicable_by_question)
    for question_id in all_question_ids:
        row = conv_rows.get(question_id)
        declaring_fips = row.val_b if row else 0
        distinct_current = row.val_a if row else 0
        top = top_by_question.get(question_id)
        convergence.append(
            {
                "questionId": question_id,
                "declaringFips": declaring_fips,
                "distinctCurrent": distinct_current,
                "topKey": top.fer_key if top else None,
                "topLabel": top.fer_key if top else None,
                "topCount": top.n if top else 0,
                "agreed": declaring_fips >= 2 and distinct_current == 1,
                # spec §11.3 amendment: additive, matches matrix.ts's Convergence.
                "notApplicableFips": not_applicable_by_question.get(question_id, 0),
            }
        )
    convergence.sort(key=lambda r: r["questionId"])

    # Candidate pairs (exact below the threshold, LSH above), then one
    # rescore-fetch statement, exactly as `clusters_view`. Scoped to this
    # population for the same reason as `clusters_view` above.
    hot_bucket_rows = list(
        db.execute(
            select(
                LshHotBucket.representative_fip_id,
                LshHotBucket.member_count,
                LshHotBucket.band_index,
                LshHotBucket.band_hash,
                # Round-3 fix (item C): fetched at no extra statement cost
                # (same select, one more column) -- its max is folded into
                # this view's ETag freshness stamp below, so a hot-bucket
                # refresh (which changes `topClusters`/`hotBuckets` in this
                # view's body without touching `projection_epoch` or any
                # member's `updated_at`) always changes the ETag too.
                LshHotBucket.computed_at,
            ).where(LshHotBucket.representative_fip_id.in_(fip_ids))
        )
    )
    if pop.count <= settings.dashboard_exact_pairs_max_fips:
        pairs = [
            (fip_ids[i], fip_ids[j])
            for i in range(len(fip_ids))
            for j in range(i + 1, len(fip_ids))
        ]
        rescored_ids = fip_ids
    else:
        pairs = _lsh_candidate_pairs(db, fip_ids, settings)
        rescored_ids = sorted(
            {i for pair in pairs for i in pair} | {r.representative_fip_id for r in hot_bucket_rows}
        )

    fip_data = fetch_fip_data(db, rescored_ids)
    edges = _score_edges(fip_data, pairs, weighting=weighting, statuses="current", min_sim=0.0)

    histogram = [
        {"bucket": i, "from": i / buckets, "to": (i + 1) / buckets, "count": 0}
        for i in range(buckets)
    ]
    principle_ids = sorted({p for e in edges for p in e.per_principle})
    principle_buckets: dict[str, list[int]] = {p: [0] * buckets for p in principle_ids}
    for e in edges:
        idx = min(int(e.score * buckets), buckets - 1)
        histogram[idx]["count"] += 1
        for p, v in e.per_principle.items():
            pidx = min(int(v * buckets), buckets - 1)
            principle_buckets.setdefault(p, [0] * buckets)[pidx] += 1

    # Same reasoning as `clusters_view`: a dict built from `pop.members`
    # (already resolved, one statement) instead of a `_readable()` call per
    # node/member.
    readable_by_id = {m.fip_id: m.readable_individually for m in pop.members}

    def _readable_fn(fip_id: str) -> bool:
        return readable_by_id.get(fip_id, False)

    # Confirmed finding #7: rescoped, not the global `member_count`.
    hot_groups = _scoped_hot_groups(db, fip_ids, hot_bucket_rows)
    # spec §4.4/D6: clustering is connected components over the
    # *thresholded* graph -- `edges` here is deliberately unthresholded
    # (min_sim=0.0 above) so the histogram/principleBuckets see the full
    # distribution; clustering itself must not connect two FIPs on a
    # near-zero score.
    cluster_min_sim = settings.dashboard_cluster_min_sim
    thresholded_edges = [e for e in edges if e.score >= cluster_min_sim]
    top_clusters = _build_clusters(
        rescored_ids, thresholded_edges, fip_data, hot_groups, limit=10, readable=_readable_fn
    )
    hot_buckets_out = [
        {
            # `size` is now population-scoped (`_scoped_hot_groups`,
            # confirmed finding #7) -- no longer the whole-table count.
            "size": member_count,
            "representativeFipId": rep_id,
            # `meanSimilarityEstimate` was a hard-coded `0.94` presented as
            # a measurement (confirmed finding #7). Computing it honestly
            # needs the other members of the bucket (spec §4.4: "a random
            # sample of 200 members ... exactly scored"), which this
            # function does not fetch (only the representative, to stay
            # inside the statement budget) -- so the field is omitted
            # rather than fabricated. `frontend/src/types/dashboard.ts`'s
            # `HotBucket.meanSimilarityEstimate` already documents this as
            # "may be absent or null" and tells the UI to render the size
            # regardless, so omitting it here needs no frontend change.
        }
        for rep_id, member_count in hot_groups
        if _readable_fn(rep_id)
    ]

    scatter_available = pop.count <= settings.dashboard_live_max_fips_scatter
    data: dict[str, Any] = {
        "histogram": histogram,
        "principleBuckets": principle_buckets,
        "convergence": convergence,
        "topClusters": top_clusters,
        "hotBuckets": hot_buckets_out,
        "scatterAvailable": scatter_available,
    }
    if scatter_available:
        readable_ids = [i for i in fip_ids if _readable_fn(i)]
        readable_id_set = set(readable_ids)
        # spec §11.3 amendment: `clusterId` per node, from the *same*
        # thresholded connected-components computation as `topClusters` --
        # so the scatter can colour by cluster without re-deriving them.
        components = similarity.cluster_edges(readable_ids, [(e.a, e.b) for e in thresholded_edges])
        cluster_id_by_fip: dict[str, str] = {}
        for representative, members in components.items():
            for member in members:
                cluster_id_by_fip[member] = representative
        data["nodes"] = [
            {
                "id": i,
                "label": fip_data.get(i, FipData()).label or i,
                "clusterId": cluster_id_by_fip.get(i, i),
            }
            for i in readable_ids
        ]
        # spec §11.3 amendment: edges thresholded at CLUSTER_MIN_SIM,
        # ordered by similarity descending, capped at
        # FIPM_DASHBOARD_MAP_EDGE_CAP, with edgesTruncated disclosed --
        # an uncapped edge list scales with the population (300 FIPs alone
        # admits 44,850 pairs), which this view's whole design avoids
        # elsewhere.
        scatter_edges_all = sorted(
            (e for e in thresholded_edges if e.a in readable_id_set and e.b in readable_id_set),
            key=lambda e: -e.score,
        )
        edge_cap = settings.dashboard_map_edge_cap
        data["edges"] = [
            {"a": e.a, "b": e.b, "similarity": e.score} for e in scatter_edges_all[:edge_cap]
        ]
        data["edgesTruncated"] = len(scatter_edges_all) > edge_cap

    scope = auth_scope_for(spec, viewer)
    max_updated_at = max((m.updated_at for m in pop.members), default=None)
    # Round-3 fix (item C): see the matching comment in `clusters_view` --
    # `hot_bucket_rows` (fetched above, no extra statement) always changes
    # `computed_at` on a refresh, so folding its max into the freshness
    # stamp `build_etag` hashes makes a hot-bucket refresh always change
    # this view's ETag too.
    hot_bucket_max = max((r.computed_at for r in hot_bucket_rows), default=None)
    if hot_bucket_max is not None and (max_updated_at is None or hot_bucket_max > max_updated_at):
        max_updated_at = hot_bucket_max
    return _minimal_envelope(
        "map",
        population_hash(canonicalise_spec(spec), scope)[:16],
        pop.count,
        data,
        scope=scope,
        params={"buckets": buckets, "weighting": weighting},
        epoch=pop.current_epoch,
        max_updated_at=max_updated_at,
    )


# ---------------------------------------------------------------------------
# Typeahead (Builder brief B item 6): up to 20 readable FIPs matching `q`,
# for picking the subject FIP of the neighbours panel. Same authorization
# and k-anonymity rules as the other views.
# ---------------------------------------------------------------------------


def _escape_ilike(text: str) -> str:
    """spec §3.7: `q` is matched "never interpolated -- the same discipline
    as spec 11 §3.2's `q`" -- the query is already parameterised (no string
    interpolation into SQL), so this isn't an injection fix, but `%`/`_` are
    still SQL `LIKE` wildcards *inside* the parameter value itself; an
    unescaped `q` like `"a_b"` would match `"aXb"` too. Confirmed finding
    #8."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def typeahead_view(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    q: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """spec §3.7 (amendment 11.4): `GET /api/dashboard/fips`. §2.4's
    k-anonymity threshold does **not** apply here -- every row named is a
    FIP the viewer may already fetch by id (`readable_individually`), and
    applying k-anonymity would 403 the very small workshop session it
    exists to protect.

    Confirmed finding #8: an empty `q` used to return `[]`; spec §3.7 says
    it "lists the population's FIPs in `updated_at DESC` order, which is
    what the panel shows before the user types" -- fixed below. Also adds
    `total`/`truncated`, which `FipLookupResponse` in
    `frontend/src/api/dashboard.ts` already declares (optional) but this
    function never populated, and escapes `%`/`_` in the `ilike` pattern.

    Round-3 fix (item A): local and network candidates used to be fetched
    as two *unbounded* Python lists (`local_rows`/`network_rows`, no SQL
    `LIMIT` on either statement) and concatenated (`all_rows = local_rows +
    network_rows`) before slicing `[offset:offset+limit]` in Python. Two
    bugs followed from that: (1) with `offset` capped at 200, any
    population with 220+ readable *local* FIPs made every network FIP
    unreachable -- they always sat past the slice window, even on an exact
    `q` match, because concatenation puts every local row before the first
    network row regardless of how the two interleave under the real
    ordering. (2) with an empty `q` on a 100k-row population, both
    statements had no `LIMIT` at all, so *all* matching rows -- up to the
    whole readable population -- were pulled into Python only to return
    20. Fixed by building one SQL `UNION ALL` of both sources (as a
    subquery) and applying `ORDER BY`/`LIMIT`/`OFFSET` exactly once over
    the combined set, so ordering and pagination are computed by SQL
    across both sources together -- no source can push the other out of
    reach -- and at most `limit` rows (plus one small, constant-size count
    statement) are ever materialized in Python, regardless of population
    size."""
    limit = min(max(limit, 1), 20)
    offset = min(max(offset, 0), 200)
    pop = resolve_population(db, spec, viewer)

    q_norm = (q or "").strip()
    has_query = bool(q_norm)
    escaped = _escape_ilike(q_norm)

    readable_ids = [m.fip_id for m in pop.members if m.readable_individually]
    local_ids = [i for i in readable_ids if not _is_network_id(i)]
    network_ids = [i for i in readable_ids if _is_network_id(i)]

    branches = []
    if local_ids:
        local_facets = aliased(FipFacets)
        local_select = (
            select(
                Fip.id.label("fip_id"),
                Fip.title.label("label"),
                local_facets.area_key.label("area_key"),
                Fip.updated_at.label("updated_at"),
            )
            .outerjoin(
                local_facets, and_(local_facets.fip_id == Fip.id, local_facets.source == "local")
            )
            .where(Fip.id.in_(local_ids))
        )
        if has_query:
            local_select = local_select.where(Fip.title.ilike(f"%{escaped}%", escape="\\"))
        branches.append(local_select)

    if network_ids:
        network_area_key = case(
            (
                NetworkFip.questionnaire_id.isnot(None),
                NetworkFip.questionnaire_id.op("||")(literal("@")).op("||")(
                    NetworkFip.questionnaire_version
                ),
            ),
            else_=literal(None),
        )
        network_select = select(
            NetworkFip.fip_id.label("fip_id"),
            NetworkFip.label.label("label"),
            network_area_key.label("area_key"),
            NetworkFip.fetched_at.label("updated_at"),
        ).where(NetworkFip.fip_id.in_(network_ids))
        if has_query:
            network_select = network_select.where(
                NetworkFip.label.ilike(f"%{escaped}%", escape="\\")
            )
        branches.append(network_select)

    if not branches:
        return {"items": [], "total": 0, "truncated": False}

    combined = (
        union_all(*branches).subquery("typeahead_candidates")
        if len(branches) > 1
        else branches[0].subquery("typeahead_candidates")
    )

    total = db.execute(select(func.count()).select_from(combined)).scalar_one()

    page_stmt = select(
        combined.c.fip_id,
        combined.c.label,
        combined.c.area_key,
        combined.c.updated_at,
    )
    if has_query:
        page_stmt = page_stmt.order_by(combined.c.label.asc(), combined.c.fip_id.asc())
    else:
        page_stmt = page_stmt.order_by(combined.c.updated_at.desc(), combined.c.fip_id.asc())
    page_stmt = page_stmt.limit(limit).offset(offset)

    page = list(db.execute(page_stmt))
    items = [
        {
            "fipId": r.fip_id,
            "label": r.label or r.fip_id,
            "areaKey": r.area_key,
            "updatedAt": r.updated_at.isoformat().replace("+00:00", "Z")
            if r.updated_at is not None
            else None,
        }
        for r in page
    ]
    return {"items": items, "total": total, "truncated": total > offset + len(page)}


# ---------------------------------------------------------------------------
# refresh job: recompute `lsh_hot_buckets` from the full `fip_signature_
# bands` table (spec §4.4) -- global, not scoped to any one population.
# ---------------------------------------------------------------------------


def refresh_hot_buckets(db: Session) -> int:
    settings = get_settings()
    bucket_max = settings.dashboard_lsh_bucket_max
    stmt = (
        select(
            FipSignatureBand.band_index,
            FipSignatureBand.band_hash,
            func.count().label("member_count"),
            func.min(FipSignatureBand.fip_id).label("representative_fip_id"),
        )
        .group_by(FipSignatureBand.band_index, FipSignatureBand.band_hash)
        .having(func.count() > bucket_max)
    )
    rows = list(db.execute(stmt))
    db.query(LshHotBucket).delete()
    now = datetime.now(UTC)
    for row in rows:
        db.add(
            LshHotBucket(
                band_index=row.band_index,
                band_hash=row.band_hash,
                member_count=row.member_count,
                representative_fip_id=row.representative_fip_id,
                computed_at=now,
            )
        )
    db.commit()
    return len(rows)
