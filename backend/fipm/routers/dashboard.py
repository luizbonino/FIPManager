"""spec 13-fip-dashboard.md §3: `GET /api/dashboard/{coverage,adoption,gaps,
evolution}` (+ `.csv` siblings), `GET|POST /api/dashboard/populations`
(brief A) and, brief B: `GET /api/dashboard/similarity/{pair,neighbours,
clusters,map}` (+ `.csv` siblings), `GET /api/dashboard/fips` (typeahead), and
`POST /api/dashboard/refresh`. The four base views and `clusters`/`map` are
routed through `fipm.dashboard.snapshots.get_or_compute` (§5) so a
population above the live tier is served from a stored snapshot instead of
brief A's `409 snapshot_required` placeholder; `pair`/`neighbours` never
touch the snapshot table at all (§5.2: "always live")."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from fipm.auth import check_anonymous_population_rate_limit
from fipm.authz import optional_user
from fipm.config import get_settings
from fipm.dashboard import DashboardError
from fipm.dashboard import snapshots as snapshots_module
from fipm.dashboard.csvout import (
    adoption_csv,
    clusters_csv,
    coverage_csv,
    evolution_csv,
    gaps_csv,
    map_csv,
    neighbours_csv,
    pair_csv,
)
from fipm.dashboard.populations import (
    auth_scope_for,
    canonicalise_spec,
    check_k_anonymity,
    decode_inline_pop,
    parse_population_spec,
    population_hash,
    resolve_population,
    shorthand_spec,
)
from fipm.dashboard.similarity_views import (
    clusters_view,
    map_view,
    neighbours_view,
    pair_view,
    typeahead_view,
)
from fipm.dashboard.snapshots import PendingResult
from fipm.dashboard.views import (
    adoption_view,
    coverage_view,
    estimated_cells,
    evolution_view,
    gaps_view,
)
from fipm.db import get_db
from fipm.models import DashboardPopulation, DashboardSnapshot, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _require_enabled() -> None:
    if not get_settings().dashboard_enabled:
        raise HTTPException(status_code=503, detail="dashboard_disabled")


def _dashboard_error_response(exc: DashboardError) -> Response:
    return Response(
        content=json.dumps(exc.body),
        status_code=exc.status_code,
        media_type="application/json",
    )


def _resolve_spec(
    db: Session,
    population: str | None,
    pop: str | None,
) -> dict[str, Any]:
    if population:
        row = db.get(DashboardPopulation, population)
        if row is None:
            raise DashboardError(404, {"detail": "population_not_found"})
        # Confirmed finding #10 (investigated, not changed): unlike
        # `GET /populations/{hash}`, this resolves *any* saved population's
        # `spec` regardless of `row.owner_id`/`auth_scope`, for any caller.
        # This is safe against a FIP-identity leak: every view/CSV route
        # below feeds this `spec` into `resolve_population(db, spec,
        # <the current request's own viewer>)`, which re-runs §2.2's full
        # security predicate for *that* viewer -- never the saved row's
        # owner -- so the effective population a stranger gets back is
        # always bounded by what the stranger could already see. Adding the
        # `GET /populations/{hash}` ownership check here would also break
        # the deliberate sharing story of §2.1 ("a facilitator can share a
        # URL"): a `pub`-scope save is meant to be resolvable by anyone
        # holding the hash, and a `u:`-scope save's *content* still can't
        # leak anything through this path for the reason above. The one
        # residual disclosure is metadata, not FIP content: a stranger who
        # already holds (guesses, is sent) another user's `u:`-scope hash
        # learns which population *terms* (e.g. `session:<id>`) that user
        # saved -- population hashes are opaque 32-hex-char SHA-256
        # digests, not enumerable, so this is not considered worth trading
        # away the sharing behaviour for.
        #
        # Round-3 fix (item D): `row.spec` is stored pre-parsed (it was
        # `parse_population_spec`'s own output at save time, per the
        # `POST /populations` handler above), but a row written before a
        # schema change, or corrupted some other way, can no longer match
        # that shape -- e.g. a missing `include` key. The `pop=` branch
        # below always re-validates through `parse_population_spec`, which
        # raises a clean `DashboardError` (400 `invalid_population`) for
        # anything structurally wrong; re-running the saved spec through
        # the same function gives this branch the identical guarantee
        # instead of letting a malformed row surface as an unhandled
        # `KeyError` (500) the first time some downstream reader indexes
        # into it.
        return parse_population_spec(row.spec)
    if pop:
        shorthand = shorthand_spec(pop)
        raw = shorthand if shorthand is not None else decode_inline_pop(pop)
        return parse_population_spec(raw)
    # spec §9 A8's network-first default needs an ingest to have run; the
    # frontend supplies `pop=network` itself once `GET /api/dashboard/
    # populations` reports `networkIngestedAt`, so this fallback (no
    # population param at all) is the public population, same as brief A.
    return parse_population_spec({"include": [{"kind": "public"}]})


def _cache_control(scope: str) -> str:
    if scope == "pub":
        return "public, max-age=0, must-revalidate"
    return "private, max-age=0, must-revalidate"


def _respond(request: Request, envelope: dict[str, Any]) -> Response:
    etag = envelope["etag"]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=json.dumps(envelope),
        media_type="application/json",
        headers={
            "ETag": etag,
            "Cache-Control": _cache_control(envelope["population"]["authScope"]),
        },
    )


def _pending_response(result: PendingResult) -> Response:
    body = {
        "status": "computing",
        "retryAfter": result.retry_after,
        "stalePayload": result.stale_payload,
        "degraded": result.degraded,
    }
    return Response(
        content=json.dumps(body),
        status_code=202,
        media_type="application/json",
        headers={"Retry-After": str(result.retry_after)},
    )


def _respond_result(request: Request, result: dict[str, Any] | PendingResult) -> Response:
    if isinstance(result, PendingResult):
        return _pending_response(result)
    return _respond(request, result)


def _csv_response(view: str, phash: str, csv_text: str) -> Response:
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{view}-{phash[:8]}.csv"'},
    )


def _csv_result_response(
    view: str, phash: str, result: dict[str, Any] | PendingResult, render
) -> Response:
    if isinstance(result, PendingResult):
        # A stale/pending snapshot has no bound population hash handy for
        # the filename; the payload (if any) is rendered from the stale
        # copy so a CSV link still produces *something* rather than an
        # opaque download failure.
        if result.stale_payload is None:
            return Response(status_code=202, headers={"Retry-After": str(result.retry_after)})
        return _csv_response(view, "pending", render(result.stale_payload))
    return _csv_response(view, phash, render(result["data"]))


@router.get("/coverage")
def get_coverage(
    request: Request,
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    groupBy: str = Query(default="subPrinciple"),  # noqa: N803 - camelCase wire param
    scope: str = Query(default="any"),
    includeAssurance: int = Query(default=0),  # noqa: N803
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"groupBy": groupBy, "scope": scope, "includeAssurance": bool(includeAssurance)}
        result = snapshots_module.get_or_compute(
            db,
            "coverage",
            spec,
            user,
            compute=lambda pop: coverage_view(
                db,
                spec,
                user,
                group_by=groupBy,
                scope=scope,
                include_assurance=bool(includeAssurance),
                pop=pop,
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond_result(request, result)


@router.get("/coverage.csv")
def get_coverage_csv(
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    groupBy: str = Query(default="subPrinciple"),  # noqa: N803
    scope: str = Query(default="any"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"groupBy": groupBy, "scope": scope, "csv": True}
        result = snapshots_module.get_or_compute(
            db,
            "coverage",
            spec,
            user,
            compute=lambda pop: coverage_view(
                db, spec, user, group_by=groupBy, scope=scope, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
        phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, user))
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_result_response("coverage", phash, result, coverage_csv)


@router.get("/adoption")
def get_adoption(
    request: Request,
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    groupBy: str = Query(default="fer"),  # noqa: N803
    status: str = Query(default="current"),
    catalogued: str = Query(default="any"),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {
            "groupBy": groupBy,
            "status": status,
            "catalogued": catalogued,
            "limit": limit,
            "offset": offset,
        }
        result = snapshots_module.get_or_compute(
            db,
            "adoption",
            spec,
            user,
            compute=lambda pop: adoption_view(
                db,
                spec,
                user,
                group_by=groupBy,
                status=status,
                catalogued=catalogued,
                limit=limit,
                offset=offset,
                pop=pop,
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond_result(request, result)


@router.get("/adoption.csv")
def get_adoption_csv(
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    status: str = Query(default="current"),
    catalogued: str = Query(default="any"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"status": status, "catalogued": catalogued, "csv": True}
        result = snapshots_module.get_or_compute(
            db,
            "adoption",
            spec,
            user,
            compute=lambda pop: adoption_view(
                db,
                spec,
                user,
                status=status,
                catalogued=catalogued,
                limit=settings.dashboard_csv_max_rows,
                offset=0,
                pop=pop,
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
        phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, user))
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_result_response("adoption", phash, result, adoption_csv)


@router.get("/gaps")
def get_gaps(
    request: Request,
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    groupBy: str = Query(default="subPrinciple"),  # noqa: N803
    minShare: float = Query(default=0.0),  # noqa: N803
    limit: int = Query(default=500),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"minShare": minShare, "limit": limit, "offset": offset}
        result = snapshots_module.get_or_compute(
            db,
            "gaps",
            spec,
            user,
            compute=lambda pop: gaps_view(
                db, spec, user, min_share=minShare, limit=limit, offset=offset, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond_result(request, result)


@router.get("/gaps.csv")
def get_gaps_csv(
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"csv": True}
        result = snapshots_module.get_or_compute(
            db,
            "gaps",
            spec,
            user,
            compute=lambda pop: gaps_view(
                db, spec, user, limit=settings.dashboard_csv_max_rows, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
        phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, user))
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_result_response("gaps", phash, result, gaps_csv)


@router.get("/evolution")
def get_evolution(
    request: Request,
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    groupBy: str = Query(default="subPrinciple"),  # noqa: N803
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"groupBy": groupBy, "limit": limit, "offset": offset}
        result = snapshots_module.get_or_compute(
            db,
            "evolution",
            spec,
            user,
            compute=lambda pop: evolution_view(
                db, spec, user, group_by=groupBy, limit=limit, offset=offset, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond_result(request, result)


@router.get("/evolution.csv")
def get_evolution_csv(
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"csv": True}
        result = snapshots_module.get_or_compute(
            db,
            "evolution",
            spec,
            user,
            compute=lambda pop: evolution_view(
                db, spec, user, limit=settings.dashboard_csv_max_rows, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_live_max_cells,
            cost_metric=estimated_cells,
        )
        phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, user))
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_result_response("evolution", phash, result, evolution_csv)


# ---------------------------------------------------------------------------
# §3.3/§4 similarity: pair, neighbours -- always live; clusters, map --
# snapshot above EXACT_PAIRS_MAX_FIPS, never computed in-request there.
# ---------------------------------------------------------------------------


@router.get("/similarity/pair")
def get_similarity_pair(
    request: Request,
    a: str = Query(...),
    b: str = Query(...),
    weighting: str = Query(default="principle"),
    statuses: str = Query(default="current"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    try:
        envelope = pair_view(db, user, a=a, b=b, weighting=weighting, statuses=statuses)
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond(request, envelope)


@router.get("/similarity/pair.csv")
def get_similarity_pair_csv(
    a: str = Query(...),
    b: str = Query(...),
    weighting: str = Query(default="principle"),
    statuses: str = Query(default="current"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    try:
        envelope = pair_view(db, user, a=a, b=b, weighting=weighting, statuses=statuses)
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_response("pair", f"{a[:8]}-{b[:8]}", pair_csv(envelope["data"]))


@router.get("/similarity/neighbours")
def get_similarity_neighbours(
    request: Request,
    fip: str = Query(...),
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    limit: int = Query(default=20),
    weighting: str = Query(default="principle"),
    statuses: str = Query(default="current"),
    minSimilarity: float = Query(default=0.0),  # noqa: N803
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    try:
        spec = _resolve_spec(db, population, pop)
        envelope = neighbours_view(
            db,
            spec,
            user,
            fip_id=fip,
            weighting=weighting,
            statuses=statuses,
            limit=limit,
            min_similarity=minSimilarity,
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond(request, envelope)


@router.get("/similarity/neighbours.csv")
def get_similarity_neighbours_csv(
    fip: str = Query(...),
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    weighting: str = Query(default="principle"),
    statuses: str = Query(default="current"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    try:
        spec = _resolve_spec(db, population, pop)
        envelope = neighbours_view(
            db, spec, user, fip_id=fip, weighting=weighting, statuses=statuses, limit=100
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_response(
        "neighbours", envelope["population"]["hash"] or "pop", neighbours_csv(envelope["data"])
    )


@router.get("/similarity/clusters")
def get_similarity_clusters(
    request: Request,
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    minSimilarity: float | None = Query(default=None),  # noqa: N803
    limit: int = Query(default=50),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"minSimilarity": minSimilarity, "limit": limit}
        result = snapshots_module.get_or_compute(
            db,
            "clusters",
            spec,
            user,
            compute=lambda pop: clusters_view(
                db, spec, user, min_similarity=minSimilarity, limit=limit, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_exact_pairs_max_fips,
            cost_metric=lambda pop: pop.count,
            allow_sync_compute=False,
            hard_max=settings.dashboard_exact_pairs_max_fips * 2000,
            hard_max_error=DashboardError(
                413,
                {
                    "detail": "similarity_population_too_large",
                    "cap": settings.dashboard_lsh_pair_cap,
                },
            ),
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond_result(request, result)


@router.get("/similarity/clusters.csv")
def get_similarity_clusters_csv(
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    minSimilarity: float | None = Query(default=None),  # noqa: N803
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"minSimilarity": minSimilarity, "limit": 200}
        result = snapshots_module.get_or_compute(
            db,
            "clusters",
            spec,
            user,
            compute=lambda pop: clusters_view(
                db, spec, user, min_similarity=minSimilarity, limit=200, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_exact_pairs_max_fips,
            cost_metric=lambda pop: pop.count,
            allow_sync_compute=False,
        )
        phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, user))
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_result_response("clusters", phash, result, clusters_csv)


@router.get("/similarity/map")
def get_similarity_map(
    request: Request,
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    buckets: int = Query(default=10),
    weighting: str = Query(default="principle"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"buckets": buckets, "weighting": weighting}
        result = snapshots_module.get_or_compute(
            db,
            "map",
            spec,
            user,
            compute=lambda pop: map_view(
                db, spec, user, buckets=buckets, weighting=weighting, pop=pop
            ),
            params=params,
            live_max=settings.dashboard_exact_pairs_max_fips,
            cost_metric=lambda pop: pop.count,
            allow_sync_compute=False,
            hard_max=settings.dashboard_exact_pairs_max_fips * 2000,
            hard_max_error=DashboardError(
                413,
                {
                    "detail": "similarity_population_too_large",
                    "cap": settings.dashboard_lsh_pair_cap,
                },
            ),
        )
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _respond_result(request, result)


@router.get("/similarity/map.csv")
def get_similarity_map_csv(
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    weighting: str = Query(default="principle"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    settings = get_settings()
    try:
        spec = _resolve_spec(db, population, pop)
        params = {"weighting": weighting, "buckets": 10}
        result = snapshots_module.get_or_compute(
            db,
            "map",
            spec,
            user,
            compute=lambda pop: map_view(db, spec, user, weighting=weighting, pop=pop),
            params=params,
            live_max=settings.dashboard_exact_pairs_max_fips,
            cost_metric=lambda pop: pop.count,
            allow_sync_compute=False,
        )
        phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, user))
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return _csv_result_response("map", phash, result, map_csv)


# ---------------------------------------------------------------------------
# Typeahead: GET /api/dashboard/fips (spec §3.7, amendment 11.4 -- Builder
# brief B item 6, specified as shipped rather than pending)
# ---------------------------------------------------------------------------


@router.get("/fips")
def get_dashboard_fips_typeahead(
    q: str = Query(default=""),
    population: str | None = Query(default=None),
    pop: str | None = Query(default=None),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    try:
        spec = _resolve_spec(db, population, pop)
        result = typeahead_view(db, spec, user, q=q, limit=limit, offset=offset)
    except DashboardError as exc:
        return _dashboard_error_response(exc)
    return Response(content=json.dumps(result), media_type="application/json")


# ---------------------------------------------------------------------------
# §2.1 populations
# ---------------------------------------------------------------------------


@router.post("/populations", status_code=201)
def save_population(
    request: Request,
    body: dict[str, Any],
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    _require_enabled()
    # Confirmed finding #9: an anonymous caller's row is `owner_id=NULL`,
    # `auth_scope='anon'` -- never shown by `list_populations` to anyone,
    # local or not, so nothing bounds how many an anonymous client can
    # insert. Signed-in callers are unaffected (their own project's existing
    # rate-limiting pattern, see `check_anonymous_fip_rate_limit`).
    if user is None:
        check_anonymous_population_rate_limit(request)
    try:
        spec = parse_population_spec(body.get("spec", body))
    except DashboardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.body.get("detail")) from exc
    canonical = canonicalise_spec(spec)
    scope = auth_scope_for(spec, user)
    phash = population_hash(canonical, scope)
    now = datetime.now(UTC)
    row = db.get(DashboardPopulation, phash)
    if row is None:
        row = DashboardPopulation(
            hash=phash,
            owner_id=user.id if user is not None else None,
            label=body.get("label"),
            spec=spec,
            auth_scope=scope,
            created_at=now,
            last_used_at=now,
        )
        db.add(row)
    else:
        row.last_used_at = now
        if body.get("label"):
            row.label = body["label"]
    db.commit()
    return {"hash": phash, "authScope": scope, "label": row.label, "spec": spec}


@router.get("/populations")
def list_populations(
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    _require_enabled()
    rows = db.query(DashboardPopulation).all()
    items = [
        {"hash": r.hash, "authScope": r.auth_scope, "label": r.label, "spec": r.spec}
        for r in rows
        if r.auth_scope == "pub" or (user is not None and r.owner_id == user.id)
    ]
    return {"items": items, "total": len(items)}


@router.get("/populations/{pop_hash}")
def get_population(
    pop_hash: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    _require_enabled()
    row = db.get(DashboardPopulation, pop_hash)
    if row is None:
        raise HTTPException(status_code=404, detail="population_not_found")
    if row.auth_scope != "pub" and (user is None or row.owner_id != user.id):
        raise HTTPException(status_code=404, detail="population_not_found")
    return {"hash": row.hash, "authScope": row.auth_scope, "label": row.label, "spec": row.spec}


# ---------------------------------------------------------------------------
# POST /api/dashboard/refresh (spec §5.3)
# ---------------------------------------------------------------------------

_REFRESH_VIEW_NAMES = ("coverage", "adoption", "gaps", "evolution", "clusters", "map")

# Confirmed finding #5: `POST /refresh` used to pass `params={}` for every
# view while every GET builds its own params dict (`groupBy`, `status`,
# `weighting`, ...) -- `params_hash({})` therefore almost never matches the
# `dashboard_snapshots` row a GET request looks up (its own primary key's
# third leg), so refresh wrote a snapshot nobody ever read and the stale row
# a viewer keeps getting survives past its TTL. These are each view's
# *default* query parameters -- the exact dict its GET route builds when
# called with no query string, i.e. what `?population=<hash>` alone resolves
# to -- so a plain refresh call updates the snapshot the default view URL
# reads. A caller wanting a *non-default* params combination refreshed still
# has no way to name it (spec's `POST /refresh` body only carries
# `population`/`views`/`force`, no per-view params) -- unchanged, and out of
# this fix's scope.
_REFRESH_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "coverage": {"groupBy": "subPrinciple", "scope": "any", "includeAssurance": False},
    "adoption": {
        "groupBy": "fer",
        "status": "current",
        "catalogued": "any",
        "limit": 50,
        "offset": 0,
    },
    "gaps": {"minShare": 0.0, "limit": 500, "offset": 0},
    "evolution": {"groupBy": "subPrinciple", "limit": 100, "offset": 0},
    "clusters": {"minSimilarity": None, "limit": 50},
    "map": {"buckets": 10, "weighting": "principle"},
}


def _refresh_compute_fn(view: str, db: Session, spec: dict[str, Any], user: User | None):
    if view == "coverage":
        return lambda pop: coverage_view(db, spec, user, pop=pop)
    if view == "adoption":
        return lambda pop: adoption_view(db, spec, user, pop=pop)
    if view == "gaps":
        return lambda pop: gaps_view(db, spec, user, pop=pop)
    if view == "evolution":
        return lambda pop: evolution_view(db, spec, user, pop=pop)
    if view == "clusters":
        return lambda pop: clusters_view(db, spec, user, pop=pop)
    if view == "map":
        return lambda pop: map_view(db, spec, user, pop=pop)
    return None


def _background_refresh(spec: dict[str, Any], user_id: str | None, views: list[str]) -> None:
    """Runs after the `202` response has already been sent (spec §5.3:
    "otherwise it runs in a `BackgroundTasks` worker") -- opens its *own*
    session, since the request's has already closed."""
    from fipm.db import SessionLocal

    with SessionLocal() as db:
        user = db.get(User, user_id) if user_id else None
        for view in views:
            if view not in _REFRESH_VIEW_NAMES:
                continue
            compute = _refresh_compute_fn(view, db, spec, user)
            try:
                snapshots_module.refresh_now(
                    db, view, spec, user, compute=compute, params=_REFRESH_DEFAULT_PARAMS[view]
                )
            except Exception:  # noqa: BLE001 - one view's failure must not stop the others
                continue


@router.post("/refresh")
def post_refresh(
    body: dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    _require_enabled()
    population_value = body.get("population")
    requested_views = [v for v in (body.get("views") or []) if v in _REFRESH_VIEW_NAMES]
    if not population_value or not requested_views:
        return _dashboard_error_response(DashboardError(400, {"detail": "invalid_population"}))

    row = db.get(DashboardPopulation, population_value)
    if row is not None:
        spec = row.spec
        is_authorized = user is not None and (user.role == "admin" or user.id == row.owner_id)
    else:
        try:
            spec = _resolve_spec(db, None, population_value)
        except DashboardError as exc:
            return _dashboard_error_response(exc)
        # An inline/shorthand population has no owner to check against --
        # admin-only, so an unauthenticated or non-admin caller cannot
        # force an expensive recompute of an arbitrary population.
        is_authorized = user is not None and user.role == "admin"
    if not is_authorized:
        return Response(
            content=json.dumps({"detail": "admin_required"}),
            status_code=403,
            media_type="application/json",
        )

    settings = get_settings()
    canonical = canonicalise_spec(spec)
    scope = auth_scope_for(spec, user)
    phash = population_hash(canonical, scope)

    for view in requested_views:
        p_hash = snapshots_module.params_hash(_REFRESH_DEFAULT_PARAMS[view])
        existing = db.get(DashboardSnapshot, (phash, view, p_hash))
        if existing is not None and existing.status == "computing":
            return _dashboard_error_response(DashboardError(409, {"detail": "refresh_in_progress"}))

    pop = resolve_population(db, spec, user)
    check_k_anonymity(pop)
    # Confirmed finding #5: comparing `pop.count` (FIPs) against
    # `dashboard_sync_max_cells` (a `fip_cells`-row budget) made the sync
    # branch fire for populations that are, in cell terms, well above it --
    # the async/202 branch below was unreachable in practice. `estimated_
    # cells` is the same FIPs-to-cells conversion `fipm.dashboard.snapshots.
    # get_or_compute` uses for the identical T1/T2 decision on every GET.
    sync = estimated_cells(pop) <= settings.dashboard_sync_max_cells

    if sync:
        for view in requested_views:
            compute = _refresh_compute_fn(view, db, spec, user)
            snapshots_module.refresh_now(
                db, view, spec, user, compute=compute, params=_REFRESH_DEFAULT_PARAMS[view]
            )
        return Response(content=json.dumps({"status": "done"}), media_type="application/json")

    for view in requested_views:
        p_hash = snapshots_module.params_hash(_REFRESH_DEFAULT_PARAMS[view])
        snapshots_module.mark_computing(db, view, phash, p_hash)
    background_tasks.add_task(
        _background_refresh, spec, user.id if user is not None else None, requested_views
    )
    return Response(
        content=json.dumps({"status": "computing", "retryAfter": 15}),
        status_code=202,
        media_type="application/json",
        headers={"Retry-After": "15"},
    )
