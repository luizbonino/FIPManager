"""spec 13-fip-dashboard.md §8.1 tests 33-38: the snapshot tier (freshness,
staleness, 202 pending, refresh authorization/concurrency), network
ingestion against spec 11's recorded fixtures, cross-boundary similarity,
and the `FIPM_DASHBOARD_ENABLED` kill switch."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fipm.ids import new_user_id
from fipm.models import (
    DashboardMeta,
    DashboardSnapshot,
    Fip,
    FipCell,
    FipDeclaration,
    FipFacets,
    NetworkFip,
    User,
    WorkshopSession,
)

KM_ID = "gofair-fip-mini"
KM_VERSION = "1.0.0"
NETWORK_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "network"
PARC_COMMUNITY_IRI = (
    "http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology"
)


def _make_session(db_session, session_id: str) -> None:
    if db_session.get(WorkshopSession, session_id) is not None:
        return
    db_session.add(
        WorkshopSession(
            id=session_id,
            join_code=session_id[:6].upper().ljust(6, "0"),
            owner_id=None,
            questionnaire_id=KM_ID,
            questionnaire_version=KM_VERSION,
            questionnaire_refs=None,
            default_language="en",
            title=session_id,
            status="open",
        )
    )
    db_session.commit()


def _make_fip(db_session, fip_id, answers, *, session_id, visibility="public", owner_id=None):
    fip = Fip(
        id=fip_id,
        owner_id=owner_id,
        session_id=session_id,
        edit_token_hash="x" if owner_id is None else None,
        visibility=visibility,
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        title=fip_id,
        community={"name": fip_id},
        related_dmps=[],
        answers=answers,
        language="en",
        license="CC0-1.0",
    )
    db_session.add(fip)
    db_session.commit()
    return fip


def _answer(question_id, *, fer_id):
    return {"questionId": question_id, "declarations": [{"ferId": fer_id, "status": "current"}]}


# ---------------------------------------------------------------------------
# 33. Snapshot written on first above-T1 request, reused on second; all four
# staleness conditions invalidate independently.
# ---------------------------------------------------------------------------


def test_snapshot_written_reused_and_staleness_conditions(app, db_session, monkeypatch, client):
    from fipm.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_live_max_cells", 1)  # force T2 for any nonempty pop
    monkeypatch.setattr(settings, "dashboard_sync_max_cells", 10_000)

    _make_session(db_session, "sim33-sess")
    fip_ids = [
        _make_fip(
            db_session,
            f"sim33-{i}",
            [_answer("F2", fer_id="https://www.doi.org/")],
            session_id="sim33-sess",
        ).id
        for i in range(3)
    ]

    r1 = client.get("/api/dashboard/coverage", params={"pop": "session:sim33-sess"})
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["tier"] == "snapshot"
    phash = body1["population"]["hash"]

    row = db_session.get(
        DashboardSnapshot,
        (phash, "coverage", db_session.query(DashboardSnapshot).one().params_hash),
    )
    assert row is not None
    assert row.status == "fresh"

    r2 = client.get("/api/dashboard/coverage", params={"pop": "session:sim33-sess"})
    body2 = r2.json()
    assert body2["computedAt"] == body1["computedAt"], "second call must reuse the stored snapshot"

    # (a) expires_at passed.
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    r3 = client.get("/api/dashboard/coverage", params={"pop": "session:sim33-sess"})
    body3 = r3.json()
    assert body3["computedAt"] != body2["computedAt"]

    # (b) projection_epoch changed.
    row = db_session.get(DashboardSnapshot, (phash, "coverage", row.params_hash))
    epoch_row = db_session.get(DashboardMeta, "projection_epoch")
    if epoch_row is None:
        db_session.add(DashboardMeta(key="projection_epoch", value=1))
    else:
        epoch_row.value = int(epoch_row.value or 0) + 1
    db_session.commit()
    r4 = client.get("/api/dashboard/coverage", params={"pop": "session:sim33-sess"})
    body4 = r4.json()
    assert body4["computedAt"] != body3["computedAt"]

    # (c) fip_count changed.
    _make_fip(
        db_session,
        "sim33-extra",
        [_answer("F2", fer_id="https://www.doi.org/")],
        session_id="sim33-sess",
    )
    r5 = client.get("/api/dashboard/coverage", params={"pop": "session:sim33-sess"})
    body5 = r5.json()
    assert body5["computedAt"] != body4["computedAt"]

    # (d) source_max_updated_at changed (a FIP inside the population edited).
    fip = db_session.get(Fip, fip_ids[0])
    fip.answers = [_answer("F2", fer_id="https://orcid.org/")]
    db_session.commit()
    r6 = client.get("/api/dashboard/coverage", params={"pop": "session:sim33-sess"})
    body6 = r6.json()
    assert body6["computedAt"] != body5["computedAt"]


# ---------------------------------------------------------------------------
# 34. 202 snapshot_pending carries Retry-After and, when a stale row
# exists, stalePayload + degraded: true.
# ---------------------------------------------------------------------------


def test_202_snapshot_pending_with_stale_payload(app, db_session, monkeypatch, client):
    from fipm.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_live_max_cells", 1000)
    monkeypatch.setattr(settings, "dashboard_sync_max_cells", 1000)

    _make_session(db_session, "sim34-sess")
    for i in range(3):
        _make_fip(
            db_session,
            f"sim34-{i}",
            [_answer("F2", fer_id="https://www.doi.org/")],
            session_id="sim34-sess",
        )

    # Within T1 first: live, no snapshot row yet.
    r0 = client.get("/api/dashboard/coverage", params={"pop": "session:sim34-sess"})
    assert r0.status_code == 200
    assert r0.json()["tier"] == "live"

    # Now push it above both T1 and T2's sync ceiling, and manufacture a
    # stale-but-present snapshot row so the 202 has something to serve as
    # `stalePayload`.
    monkeypatch.setattr(settings, "dashboard_live_max_cells", 1)
    monkeypatch.setattr(settings, "dashboard_sync_max_cells", 1)

    from fipm.dashboard.populations import (
        auth_scope_for,
        canonicalise_spec,
        parse_population_spec,
        population_hash,
    )
    from fipm.dashboard.snapshots import params_hash

    spec = parse_population_spec({"include": [{"kind": "session", "id": "sim34-sess"}]})
    phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, None))
    p_hash = params_hash({"groupBy": "subPrinciple", "scope": "any", "includeAssurance": False})
    db_session.add(
        DashboardSnapshot(
            population_hash=phash,
            view="coverage",
            params_hash=p_hash,
            status="fresh",
            payload={"rows": [], "totals": {"fips": 3, "cells": 63}, "order": []},
            payload_bytes=10,
            etag='W/"stale"',
            fip_count=3,
            source_max_updated_at=datetime.now(UTC) - timedelta(days=1),
            projection_epoch=0,
            computed_at=datetime.now(UTC) - timedelta(hours=2),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            duration_ms=5,
            error=None,
        )
    )
    db_session.commit()

    r1 = client.get("/api/dashboard/coverage", params={"pop": "session:sim34-sess"})
    assert r1.status_code == 202, r1.text
    assert r1.headers["Retry-After"] == "15"
    body = r1.json()
    assert body["status"] == "computing"
    assert body["retryAfter"] == 15
    assert body["degraded"] is True
    assert body["stalePayload"]["totals"]["fips"] == 3


# ---------------------------------------------------------------------------
# 35. refresh is owner/admin-only; a concurrent refresh 409s.
# ---------------------------------------------------------------------------


def test_refresh_authorization_and_concurrency(app, db_session, client):
    owner = User(
        id=new_user_id(),
        email="sim35-owner@example.com",
        password_hash="x",
        display_name="Owner",
        role="user",
        language="en",
    )
    admin = User(
        id=new_user_id(),
        email="sim35-admin@example.com",
        password_hash="x",
        display_name="Admin",
        role="admin",
        language="en",
    )
    db_session.add_all([owner, admin])
    db_session.commit()

    _make_session(db_session, "sim35-sess")
    _make_fip(
        db_session,
        "sim35-fip",
        [_answer("F2", fer_id="https://www.doi.org/")],
        session_id="sim35-sess",
    )

    from fipm.dashboard.populations import (
        auth_scope_for,
        canonicalise_spec,
        parse_population_spec,
        population_hash,
    )
    from fipm.models import DashboardPopulation

    spec = parse_population_spec({"include": [{"kind": "session", "id": "sim35-sess"}]})
    phash = population_hash(canonicalise_spec(spec), auth_scope_for(spec, owner))
    db_session.add(
        DashboardPopulation(
            hash=phash,
            owner_id=owner.id,
            label="sim35",
            spec=spec,
            auth_scope=auth_scope_for(spec, owner),
        )
    )
    db_session.commit()

    r = client.post("/api/dashboard/refresh", json={"population": phash, "views": ["coverage"]})
    assert r.status_code == 403, r.text

    from fipm.auth import COOKIE_NAME, create_auth_session
    from fipm.config import get_settings

    other = User(
        id=new_user_id(),
        email="sim35-other@example.com",
        password_hash="x",
        display_name="Other",
        role="user",
        language="en",
    )
    db_session.add(other)
    db_session.commit()
    _, token = create_auth_session(db_session, other, get_settings())
    client.cookies.set(COOKIE_NAME, token)
    r = client.post("/api/dashboard/refresh", json={"population": phash, "views": ["coverage"]})
    assert r.status_code == 403, r.text
    client.cookies.clear()

    _, token = create_auth_session(db_session, owner, get_settings())
    client.cookies.set(COOKIE_NAME, token)
    r = client.post("/api/dashboard/refresh", json={"population": phash, "views": ["coverage"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    from fipm.dashboard.snapshots import params_hash
    from fipm.routers.dashboard import _REFRESH_DEFAULT_PARAMS

    # Confirmed finding #5: `POST /refresh` now hashes each view's *default*
    # query params (matching what a plain `GET .../coverage?population=...`
    # would use), not `params_hash({})` -- so the row this test flips to
    # `computing` (to provoke the `409 refresh_in_progress` branch) must be
    # looked up under that same key.
    row = db_session.get(
        DashboardSnapshot, (phash, "coverage", params_hash(_REFRESH_DEFAULT_PARAMS["coverage"]))
    )
    assert row is not None
    row.status = "computing"
    db_session.commit()

    r = client.post("/api/dashboard/refresh", json={"population": phash, "views": ["coverage"]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "refresh_in_progress"
    client.cookies.clear()


# ---------------------------------------------------------------------------
# 36. ingest-network-fips against the spec 11 fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture()
def parc_seam(monkeypatch):
    from fipm import network

    parc_fips = json.loads((NETWORK_FIXTURES_DIR / "parc-fips.json").read_text())
    parc_decls = json.loads((NETWORK_FIXTURES_DIR / "parc-declarations.json").read_text())
    parc_resources = json.loads((NETWORK_FIXTURES_DIR / "parc-resources.json").read_text())

    def fake_post_sparql(settings, repo, query):
        if repo == f"type/{network.FIP_TYPE_REPO}":
            return parc_fips
        if repo == "full" and "npx:includesElement" in query:
            return parc_decls
        if repo == "full" and "fip:FAIR-Enabling-Resource" in query:
            return parc_resources
        raise AssertionError(f"unexpected repo/query: {repo}")

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)
    return network


def test_ingest_network_fips_writes_shadow_rows_no_fips_row(app, db_session, parc_seam):
    from fipm.config import get_settings
    from fipm.network_ingest import ingest_network_fips, network_fip_id

    report = ingest_network_fips(db_session, get_settings(), community_iri=PARC_COMMUNITY_IRI)
    assert report.fips_written == 1
    assert report.fips_failed == 0
    assert report.unmapped_dropped > 0

    net_id = network_fip_id(PARC_COMMUNITY_IRI)
    assert db_session.get(Fip, net_id) is None
    assert db_session.get(NetworkFip, net_id) is not None
    facets = db_session.get(FipFacets, net_id)
    assert facets is not None
    assert facets.source == "network"
    assert db_session.query(FipCell).filter_by(fip_id=net_id).count() > 0
    assert db_session.query(FipDeclaration).filter_by(fip_id=net_id).count() > 0

    from fipm.dashboard.populations import parse_population_spec, resolve_population

    without_network = resolve_population(
        db_session, parse_population_spec({"include": [{"kind": "mine"}]}), None
    )
    assert net_id not in without_network.fip_ids

    with_network = resolve_population(
        db_session, parse_population_spec({"include": [{"kind": "network"}]}), None
    )
    assert net_id in with_network.fip_ids

    # check-declarations must consider this a clean, legitimate shadow row.
    from fipm.cli import run_check_declarations

    problems = run_check_declarations(only_ids=[net_id])
    assert problems == []


# ---------------------------------------------------------------------------
# 37. Cross-boundary similarity: a local FIP's nearest neighbour in a
# public ∪ network population is the network shadow row sharing its keys.
# ---------------------------------------------------------------------------


def test_cross_boundary_similarity_local_and_network(app, db_session, parc_seam, client):
    from fipm.config import get_settings
    from fipm.network_ingest import ingest_network_fips, network_fip_id

    report = ingest_network_fips(db_session, get_settings(), community_iri=PARC_COMMUNITY_IRI)
    assert report.fips_written == 1
    net_id = network_fip_id(PARC_COMMUNITY_IRI)

    network_decls = (
        db_session.query(FipDeclaration)
        .filter(
            FipDeclaration.fip_id == net_id,
            FipDeclaration.status == "current",
            FipDeclaration.fer_id.isnot(None),
        )
        .all()
    )
    assert network_decls, (
        "the PARC fixture must carry at least one current, cataloguable declaration"
    )
    shared = network_decls[0]

    _make_session(db_session, "sim37-sess")
    local = _make_fip(
        db_session,
        "sim37-local",
        [
            {
                "questionId": shared.question_id,
                "declarations": [{"ferId": shared.fer_id, "status": "current"}],
            }
        ],
        session_id="sim37-sess",
        visibility="public",
    )

    spec = {"include": [{"kind": "session", "id": "sim37-sess"}, {"kind": "network"}]}
    import base64

    from fipm.dashboard.populations import canonicalise_spec

    encoded = base64.urlsafe_b64encode(canonicalise_spec(spec).encode()).decode().rstrip("=")
    r = client.get(
        "/api/dashboard/similarity/neighbours", params={"fip": local.id, "pop": encoded, "limit": 5}
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert any(n["fipId"] == net_id for n in data["neighbours"]), data["neighbours"]
    top = next(n for n in data["neighbours"] if n["fipId"] == net_id)
    assert top["similarity"] > 0


# ---------------------------------------------------------------------------
# 38. FIPM_DASHBOARD_ENABLED=false -> 503 everywhere, dashboardEnabled:
# false in /api/health, and no projection rows written by a FIP write.
# ---------------------------------------------------------------------------


def test_dashboard_disabled_flag(app, db_session, monkeypatch, client):
    from fipm.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_enabled", False)

    r = client.get("/api/health")
    assert r.json()["dashboardEnabled"] is False

    for path in (
        "/api/dashboard/coverage",
        "/api/dashboard/adoption",
        "/api/dashboard/gaps",
        "/api/dashboard/evolution",
        "/api/dashboard/similarity/pair?a=x&b=y",
        "/api/dashboard/similarity/neighbours?fip=x&pop=public",
        "/api/dashboard/similarity/clusters",
        "/api/dashboard/similarity/map",
        "/api/dashboard/fips?q=x",
        "/api/dashboard/populations",
    ):
        r = client.get(path)
        assert r.status_code == 503, (path, r.text)
        assert r.json()["detail"] == "dashboard_disabled"

    fip_id = _make_fip(
        db_session, "sim38-fip", [_answer("F2", fer_id="https://www.doi.org/")], session_id=None
    ).id
    assert db_session.get(FipFacets, fip_id) is None
    assert db_session.query(FipCell).filter_by(fip_id=fip_id).count() == 0
