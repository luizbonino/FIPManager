"""spec 13-fip-dashboard.md §5: the snapshot tier (T2), ETags, staleness,
freshness and `POST /api/dashboard/refresh`, plus Q7's delete-time scrub.

`get_or_compute` is the **one** entry point every snapshot-eligible view
routes through -- brief A's four views (coverage/adoption/gaps/evolution)
and brief B's `clusters`/`map` alike. It resolves the population exactly
once (never twice -- that would double the population-resolution statement
AC-16/§8.2 count), decides the T1/T2/T3 tier (§0) from that one resolution,
and only then either calls the view function directly (T1, live) or reads
or writes a `dashboard_snapshots` row (T2). Above `FIPM_DASHBOARD_SYNC_MAX_
CELLS` with no fresh snapshot, it returns a `pending` marker without ever
calling the view function (T3 -- AC-11: the compute function must not even
be invoked there).

`similarity/pair` and `similarity/neighbours` never call this module at all
(§5.2: "always live, never [snapshot]") -- their own cost is population-size
independent, so there is nothing to cache."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
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
from fipm.models import DashboardSnapshot, User

ComputeFn = Callable[[ResolvedPopulation], dict[str, Any]]


def params_hash(params: dict[str, Any]) -> str:
    """sha256 of the canonical JSON of a view's own parameters (weighting,
    status, groupBy, ...) -- the third leg of `dashboard_snapshots`'s
    primary key (spec §5.1)."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def build_etag(
    view: str,
    phash: str,
    p_hash: str,
    epoch: int,
    max_updated_at: datetime | None,
    fip_count: int,
) -> str:
    """`W/"<view>-<population_hash[:12]>-<params_hash[:8]>-<projection_epoch>
    -<max_updated_at>-<fip_count>"` (spec §3) -- the exact same formula
    brief A's `views._envelope` uses inline, factored out here so the live
    and snapshot paths can never disagree on what an ETag for the same
    inputs looks like."""
    stamp = max_updated_at.isoformat() if max_updated_at is not None else "empty"
    return f'W/"{view}-{phash[:12]}-{p_hash[:8]}-{epoch}-{stamp}-{fip_count}"'


def _aware(value: datetime | None) -> datetime | None:
    """SQLite round-trips a `DateTime(timezone=True)` value as naive
    (established convention across this codebase, see `fipm.auth`/
    `fipm.exporters`/`fipm.rdf`) -- normalise to UTC-aware before any
    comparison so a raw-from-`Fip`/`ResolvedPopulation` value and a
    raw-from-`DashboardSnapshot` value are always comparable."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _max_updated_at(pop: ResolvedPopulation) -> datetime | None:
    return max((m.updated_at for m in pop.members), default=None)


def _row_is_stale(row: DashboardSnapshot, pop: ResolvedPopulation) -> bool:
    """spec §5.3's four staleness conditions, checked independently -- any
    one of them makes the stored payload unusable as-is."""
    now = datetime.now(UTC)
    if _aware(row.expires_at) < now:
        return True
    if row.projection_epoch != pop.current_epoch:
        return True
    if row.fip_count != pop.count:
        return True
    current_max = _aware(_max_updated_at(pop))
    stored_max = _aware(row.source_max_updated_at)
    if (current_max is None) != (stored_max is None):
        return True
    if current_max is not None and stored_max is not None and current_max != stored_max:
        return True
    return False


def _snapshot_envelope(row: DashboardSnapshot, pop: ResolvedPopulation) -> dict[str, Any]:
    return {
        "population": {
            "hash": row.population_hash,
            "authScope": None,
            "fipCount": pop.count if pop.k_hidden == 0 else None,
            "label": None,
        },
        "tier": "snapshot",
        "computedAt": _aware(row.computed_at).isoformat().replace("+00:00", "Z"),
        "degraded": False,
        "degradedReason": None,
        "staleFips": None,
        "etag": row.etag,
        "data": row.payload,
    }


@dataclass
class PendingResult:
    """`fipm.routers.dashboard` turns this into `202 {"status": "computing",
    "retryAfter": ..., "stalePayload": ..., "degraded": ...}` (spec §5.3)."""

    retry_after: int
    stale_payload: Any | None
    degraded: bool


def get_or_compute(
    db: Session,
    view: str,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    compute: ComputeFn,
    params: dict[str, Any],
    live_max: int,
    cost_metric: Callable[[ResolvedPopulation], int],
    allow_sync_compute: bool = True,
    sync_max: int | None = None,
    hard_max: int | None = None,
    hard_max_error: DashboardError | None = None,
) -> dict[str, Any] | PendingResult:
    """spec §5: `live_max`/`cost_metric` together decide the T1 boundary
    (e.g. `views.estimated_cells` vs. `FIPM_DASHBOARD_LIVE_MAX_CELLS` for
    the four base views; population *count* vs.
    `FIPM_DASHBOARD_EXACT_PAIRS_MAX_FIPS` for `clusters`/`map`). `compute`
    receives the already-resolved population and must return a full
    envelope shaped like brief A's `views._envelope` output (population/
    tier/computedAt/degraded/etag/data) -- its own `tier` is overwritten
    with `"snapshot"` when this function decides to cache it.

    `allow_sync_compute=False` (`clusters`/`map`, spec §5.2: "never computed
    in-request above" their tier boundary) skips the T2-synchronous branch
    entirely -- above `live_max` with no fresh snapshot, this returns a
    `PendingResult` unconditionally and `compute` is **never** called
    (AC-11), regardless of how cheap the population might actually be to
    score; only `POST /api/dashboard/refresh` (or the `refresh-dashboard`
    cron) may compute it. The four base views keep `allow_sync_compute=True`
    (brief A's behaviour, generalised): a population between `live_max` and
    `sync_max` (default `FIPM_DASHBOARD_SYNC_MAX_CELLS`) is computed once,
    synchronously, to become a T2 snapshot.

    Returns either a ready envelope dict, or a `PendingResult`."""
    settings = get_settings()
    sync_max = settings.dashboard_sync_max_cells if sync_max is None else sync_max
    pop = resolve_population(db, spec, viewer)
    check_k_anonymity(pop)

    cost = cost_metric(pop)
    if hard_max is not None and cost > hard_max:
        raise hard_max_error or DashboardError(413, {"detail": "similarity_population_too_large"})
    if cost <= live_max:
        envelope = compute(pop)
        envelope["tier"] = "live"
        return envelope

    canonical = canonicalise_spec(spec)
    scope = auth_scope_for(spec, viewer)
    phash = population_hash(canonical, scope)
    p_hash = params_hash(params)

    row = db.get(DashboardSnapshot, (phash, view, p_hash))

    if row is not None and row.status == "fresh" and not _row_is_stale(row, pop):
        envelope = _snapshot_envelope(row, pop)
        envelope["population"]["authScope"] = scope
        return envelope

    if row is not None and row.status == "computing":
        return PendingResult(
            retry_after=15, stale_payload=row.payload, degraded=row.payload is not None
        )

    if not allow_sync_compute or cost > sync_max:
        # T3 (or a view with no synchronous-on-GET path at all): refuse to
        # compute in-request; `compute` is never called here (AC-11) -- a
        # background refresh (POST /refresh, or the `refresh-dashboard`
        # cron) is what will make this fresh.
        return PendingResult(
            retry_after=15,
            stale_payload=row.payload if row is not None else None,
            degraded=row is not None and row.payload is not None,
        )

    # T2, synchronous: compute once, store, serve.
    return _compute_and_store(db, view, phash, p_hash, pop, compute, scope)


def _compute_and_store(
    db: Session,
    view: str,
    phash: str,
    p_hash: str,
    pop: ResolvedPopulation,
    compute: ComputeFn,
    scope: str,
) -> dict[str, Any]:
    settings = get_settings()
    start = datetime.now(UTC)
    envelope = compute(pop)
    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

    data = envelope["data"]
    payload_bytes = len(json.dumps(data, separators=(",", ":")).encode("utf-8"))
    truncated = False
    if payload_bytes > settings.dashboard_snapshot_max_bytes:
        # spec §5.1: trimmed to fit rather than stored oversized. The four
        # base views and `clusters`/`map` all carry a top-level "rows" or
        # analogous list as their largest component; a generic, conservative
        # trim halves whatever list-shaped fields exist until it fits, and
        # always marks `truncated`.
        data, truncated = _trim_to_fit(data, settings.dashboard_snapshot_max_bytes)
        payload_bytes = len(json.dumps(data, separators=(",", ":")).encode("utf-8"))
    if truncated and isinstance(data, dict):
        data["truncated"] = True

    now = datetime.now(UTC)
    epoch = pop.current_epoch
    max_updated = _max_updated_at(pop)
    etag = build_etag(view, phash, p_hash, epoch, max_updated, pop.count)
    expires_at = now + timedelta(seconds=settings.dashboard_snapshot_ttl_seconds)

    row = db.get(DashboardSnapshot, (phash, view, p_hash))
    if row is None:
        row = DashboardSnapshot(
            population_hash=phash,
            view=view,
            params_hash=p_hash,
            status="fresh",
            payload=data,
            payload_bytes=payload_bytes,
            etag=etag,
            fip_count=pop.count,
            source_max_updated_at=max_updated,
            projection_epoch=epoch,
            computed_at=now,
            expires_at=expires_at,
            duration_ms=duration_ms,
            error=None,
        )
        db.add(row)
    else:
        row.status = "fresh"
        row.payload = data
        row.payload_bytes = payload_bytes
        row.etag = etag
        row.fip_count = pop.count
        row.source_max_updated_at = max_updated
        row.projection_epoch = epoch
        row.computed_at = now
        row.expires_at = expires_at
        row.duration_ms = duration_ms
        row.error = None
    db.commit()

    result = {
        "population": {
            "hash": phash,
            "authScope": scope,
            "fipCount": pop.count if pop.k_hidden == 0 else None,
            "label": None,
        },
        "tier": "snapshot",
        "computedAt": now.isoformat().replace("+00:00", "Z"),
        "degraded": False,
        "degradedReason": None,
        "staleFips": None,
        "etag": etag,
        "data": data,
    }
    return result


def _trim_to_fit(data: dict[str, Any], max_bytes: int) -> tuple[dict[str, Any], bool]:
    """Halve the largest list-valued top-level field until the payload fits
    `max_bytes`, or until further halving can no longer help (an empty
    list) -- a best-effort, view-shape-agnostic trim (spec §5.1: "trimmed
    to its top-N rows" rather than stored oversized)."""
    trimmed = dict(data)
    changed = True
    did_trim = False
    while changed and len(json.dumps(trimmed, separators=(",", ":")).encode("utf-8")) > max_bytes:
        changed = False
        list_fields = [(k, v) for k, v in trimmed.items() if isinstance(v, list) and v]
        if not list_fields:
            break
        key, biggest = max(list_fields, key=lambda kv: len(kv[1]))
        new_len = max(1, len(biggest) // 2)
        if new_len == len(biggest):
            break
        trimmed[key] = biggest[:new_len]
        changed = True
        did_trim = True
    # Confirmed finding #10: this used to return `True` unconditionally --
    # a payload that never entered the loop (already under `max_bytes`, the
    # normal case) or that hit `break` before trimming anything (no
    # list-valued field to trim) was reported `"truncated": true` even
    # though nothing was cut.
    return trimmed, did_trim


# ---------------------------------------------------------------------------
# POST /api/dashboard/refresh (spec §5.3)
# ---------------------------------------------------------------------------


def refresh_now(
    db: Session,
    view: str,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    compute: ComputeFn,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Unconditionally (re)computes and stores one snapshot row, regardless
    of the T1/T2 tier -- used by `POST /api/dashboard/refresh`'s synchronous
    branch and by `python -m fipm refresh-dashboard`. A concurrent refresh
    of the *same* `(population, view, params)` key is rejected by the
    caller checking `status == 'computing'` first (§5.3's `409
    refresh_in_progress`) -- this function itself just does the work."""
    pop = resolve_population(db, spec, viewer)
    check_k_anonymity(pop)
    canonical = canonicalise_spec(spec)
    scope = auth_scope_for(spec, viewer)
    phash = population_hash(canonical, scope)
    p_hash = params_hash(params)
    return _compute_and_store(db, view, phash, p_hash, pop, compute, scope)


def mark_computing(db: Session, view: str, phash: str, p_hash: str) -> DashboardSnapshot:
    row = db.get(DashboardSnapshot, (phash, view, p_hash))
    now = datetime.now(UTC)
    if row is None:
        row = DashboardSnapshot(
            population_hash=phash,
            view=view,
            params_hash=p_hash,
            status="computing",
            payload=None,
            payload_bytes=0,
            etag=f'W/"{view}-{phash[:12]}-{p_hash[:8]}-pending"',
            fip_count=0,
            source_max_updated_at=None,
            projection_epoch=0,
            computed_at=now,
            expires_at=now,
            duration_ms=0,
            error=None,
        )
        db.add(row)
    else:
        row.status = "computing"
    db.commit()
    return row


def drain_expired(db: Session, *, older_than_days: int = 7) -> int:
    """`refresh-dashboard`'s housekeeping half (spec §5.3): `DELETE FROM
    dashboard_snapshots WHERE expires_at < now - 7 days`."""
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = db.execute(delete(DashboardSnapshot).where(DashboardSnapshot.expires_at < cutoff))
    db.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# spec §9 Q7 -- a deleted FIP's id must not survive inside a stored
# clusters/map snapshot payload.
# ---------------------------------------------------------------------------


def scrub_snapshots_for_deleted_fip(db: Session, deleted_at: datetime) -> int:
    """spec §9 Q7's recommendation, implemented in brief B: on FIP delete,
    invalidate every `clusters`/`map` snapshot whose `source_max_updated_at`
    predates the delete -- cheap (an index scan on `ix_snap_expires` is not
    even needed; this is a small table), and it keeps the privacy notice's
    deletion promise literally true, rather than leaving the id readable
    inside a cached payload for up to `FIPM_DASHBOARD_SNAPSHOT_TTL_SECONDS`.
    Deleting (not merely expiring) the row also means the *next* request
    recomputes from the current, FIP-free population rather than serving a
    `status='computing'`-but-stale row. Returns the number of rows deleted."""
    stmt = select(DashboardSnapshot).where(
        DashboardSnapshot.view.in_(("clusters", "map")),
        (DashboardSnapshot.source_max_updated_at.is_(None))
        | (DashboardSnapshot.source_max_updated_at < deleted_at),
    )
    rows = list(db.execute(stmt).scalars())
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
    return len(rows)
