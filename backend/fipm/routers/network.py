"""spec 11-nanopub-network.md §3.2: `GET /api/network/*`, the read-only
nanopublication-network proxy. All three routes are unauthenticated
(a workshop participant has no account) and read-only."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fipm import network
from fipm.config import Settings, get_settings
from fipm.db import get_db
from fipm.models import Fer

router = APIRouter(prefix="/network", tags=["network"])


def _require_network_enabled(settings: Settings) -> None:
    if not settings.network_enabled:
        raise HTTPException(status_code=503, detail="network_disabled")


def _to_http(exc: network.NetworkError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.code)


def _iso(cached_at: float) -> str:
    return datetime.fromtimestamp(cached_at, tz=UTC).isoformat().replace("+00:00", "Z")


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _envelope(
    body: dict[str, Any], cached_at: float, stale: bool, settings: Settings
) -> dict[str, Any]:
    result = {**body, "cachedAt": _iso(cached_at), "source": settings.nanopub_query_url}
    if stale:
        result["stale"] = True
    return result


@router.get("/fip-communities")
def list_fip_communities(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    settings = get_settings()
    _require_network_enabled(settings)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    try:
        items, cached_at, stale = network.get_fip_communities(settings)
    except network.NetworkError as exc:
        raise _to_http(exc) from exc

    if q:
        needle = _normalise(q)
        items = [item for item in items if needle in _normalise(item["label"])]

    total = len(items)
    page = items[offset : offset + limit]
    return _envelope({"items": page, "total": total}, cached_at, stale, settings)


# ---------------------------------------------------------------------------
# GET /network/fips/{communityIri}: §3.3's shape, `inCatalogue` resolved here
# (against the `fers` table) since fipm.network is DB-free.
# ---------------------------------------------------------------------------


def _build_fer_indexes(db: Session) -> tuple[dict[str, Fer], dict[str, Fer], dict[str, Fer]]:
    """spec §3.3: the three lookup indexes `_match_in_catalogue` tries, in
    priority order -- by `Fer.id`, by homepage (`Fer.homepage` or
    `Fer.id` itself, the `skos:exactMatch` case), by exact case-folded
    label (one entry per `|`-separated part of `Fer.label_search`)."""
    by_id: dict[str, Fer] = {}
    by_homepage: dict[str, Fer] = {}
    by_label: dict[str, Fer] = {}
    for row in db.query(Fer).all():
        by_id[row.id] = row
        if row.homepage:
            by_homepage.setdefault(row.homepage, row)
        by_homepage.setdefault(row.id, row)
        for part in (row.label_search or "").split("|"):
            if part:
                by_label.setdefault(part, row)
    return by_id, by_homepage, by_label


def _match_in_catalogue(
    resource: dict[str, Any],
    by_id: dict[str, Fer],
    by_homepage: dict[str, Fer],
    by_label: dict[str, Fer],
) -> dict[str, str] | None:
    row = by_id.get(resource["iri"])
    if row is not None:
        return {"ferId": row.id, "matchedBy": "ferId"}
    homepage = resource.get("homepage")
    if homepage:
        row = by_homepage.get(homepage)
        if row is not None:
            return {"ferId": row.id, "matchedBy": "homepage"}
    label = resource.get("label")
    if label:
        row = by_label.get(label.casefold())
        if row is not None:
            return {"ferId": row.id, "matchedBy": "label"}
    return None


def _resolve_in_catalogue(db: Session, payload: dict[str, Any]) -> None:
    by_id, by_homepage, by_label = _build_fer_indexes(db)
    for bucket in (*payload["questions"], *payload["unmapped"]):
        for decl in bucket["declarations"]:
            resource = decl.get("resource")
            if resource is not None:
                resource["inCatalogue"] = _match_in_catalogue(
                    resource, by_id, by_homepage, by_label
                )


@router.get("/fips/{community_iri:path}")
def get_network_fip(community_iri: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    _require_network_enabled(settings)

    try:
        payload, cached_at, stale = network.get_community_fip(settings, community_iri)
    except network.NetworkError as exc:
        raise _to_http(exc) from exc

    # The community's own label isn't part of Q1/Q2/Q3 -- it's the Q0 list's
    # job (spec §3.1). Best-effort lookup against the (cached) community
    # list; None if the upstream call fails or the community isn't in it
    # (shouldn't happen for a community that just answered Q1, but a 502
    # here must never turn a working fip-detail response into a failure).
    label = None
    try:
        communities, _, _ = network.get_fip_communities(settings)
    except network.NetworkError:
        communities = []
    for item in communities:
        if item["iri"] == community_iri:
            label = item["label"]
            break
    payload["community"]["label"] = label

    _resolve_in_catalogue(db, payload)

    return _envelope(payload, cached_at, stale, settings)


@router.get("/fers")
def search_network_fers(q: str = "", limit: int = 20) -> dict[str, Any]:
    """v2 roadmap (spec §7 Q8): shipped and testable, not yet wired into
    `FerPicker.vue`."""
    settings = get_settings()
    _require_network_enabled(settings)
    limit = max(1, min(limit, 200))

    try:
        items, cached_at, stale = network.search_fers(settings, q, limit)
    except network.NetworkError as exc:
        raise _to_http(exc) from exc

    return _envelope({"items": items, "total": len(items)}, cached_at, stale, settings)
