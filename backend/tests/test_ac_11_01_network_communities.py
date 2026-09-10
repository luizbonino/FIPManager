"""spec 11-nanopub-network.md §3.2/§3.4, builder brief A tests 1-7:
`GET /api/network/fip-communities`.

Fixtures are injected by monkeypatching `fipm.network._get_grlc` /
`_post_sparql` (the two seams) -- never a live request (conftest.py's
autouse `_guard_network_calls` fixture enforces this: an un-patched call
raises immediately rather than attempting one)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm import network
from fipm.config import get_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "network"
COMMUNITIES_FIXTURE = json.loads((FIXTURES_DIR / "fip-communities.json").read_text())


@pytest.fixture()
def communities_seam(monkeypatch):
    """Counts calls and serves the recorded fixture for Q0's exact
    (artifactCode, queryName); any other call raises, so a test that
    accidentally triggers Q1/Q2/Q3/Q4 fails loudly instead of silently
    reusing this fixture."""
    calls = {"n": 0}

    def fake_get_grlc(settings, artifact_code, query_name):
        assert artifact_code == network.Q0_ARTIFACT_CODE
        assert query_name == network.Q0_QUERY_NAME
        calls["n"] += 1
        return COMMUNITIES_FIXTURE

    monkeypatch.setattr(network, "_get_grlc", fake_get_grlc)
    return calls


def test_dedupe_keeps_longest_label_and_max_fip_count():
    """Unit-level: the dedupe algorithm itself, on a synthetic pair -- the
    longer label and the larger fip_count each win independently."""
    bindings = [
        {
            "community": {"value": "http://example.org/c1"},
            "community_label": {"value": "Short"},
            "fip_count": {"value": "3"},
        },
        {
            "community": {"value": "http://example.org/c1"},
            "community_label": {"value": "A Much Longer Label"},
            "fip_count": {"value": "5"},
        },
    ]
    result = network._dedupe_communities(bindings)
    assert len(result) == 1
    assert result[0] == {
        "iri": "http://example.org/c1",
        "label": "A Much Longer Label",
        "fipCount": 5,
    }


def test_list_communities_dedupes_real_duplicate(client, communities_seam):
    r = client.get("/api/network/fip-communities?limit=200")
    assert r.status_code == 200, r.text
    body = r.json()

    raw = COMMUNITIES_FIXTURE["results"]["bindings"]
    by_iri: dict[str, list[dict]] = {}
    for row in raw:
        by_iri.setdefault(row["community"]["value"], []).append(row)
    duplicated_iri = next(iri for iri, rows in by_iri.items() if len(rows) > 1)
    expected = network._dedupe_communities(raw)
    expected_entry = next(e for e in expected if e["iri"] == duplicated_iri)

    items_by_iri = {item["iri"]: item for item in body["items"]}
    assert duplicated_iri in items_by_iri
    assert items_by_iri[duplicated_iri]["label"] == expected_entry["label"]
    assert items_by_iri[duplicated_iri]["fipCount"] == expected_entry["fipCount"]
    # No IRI appears twice.
    assert len(items_by_iri) == len(body["items"])
    assert body["total"] == len(expected)
    assert body["cachedAt"]
    assert body["source"]


def test_q_matches_case_insensitively_and_second_label_half(client, communities_seam):
    r = client.get("/api/network/fip-communities?q=actris&limit=200")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    for item in body["items"]:
        assert "actris" in item["label"].casefold()

    # A label of the shape "Short | Long name" must match on the second half
    # too (spec §3.1's own duplicate-label example is exactly this shape).
    all_items = network._dedupe_communities(COMMUNITIES_FIXTURE["results"]["bindings"])
    pipe_labelled = next(item for item in all_items if "|" in item["label"])
    second_half = pipe_labelled["label"].split("|", 1)[1].strip()
    needle = second_half.split()[0]
    r2 = client.get(f"/api/network/fip-communities?q={needle}&limit=200")
    assert r2.status_code == 200
    found = {item["iri"] for item in r2.json()["items"]}
    assert pipe_labelled["iri"] in found


def test_pagination(client, communities_seam):
    full = client.get("/api/network/fip-communities?limit=200").json()
    total = full["total"]
    assert total > 2

    page = client.get("/api/network/fip-communities?limit=2&offset=1").json()
    assert page["total"] == total
    assert len(page["items"]) == 2
    assert page["items"] == full["items"][1:3]


def test_second_call_within_ttl_hits_no_upstream(client, communities_seam):
    r1 = client.get("/api/network/fip-communities")
    assert r1.status_code == 200
    assert communities_seam["n"] == 1
    r2 = client.get("/api/network/fip-communities")
    assert r2.status_code == 200
    assert communities_seam["n"] == 1  # served from cache, no second call


def test_ttl_expiry_triggers_second_call(client, communities_seam, monkeypatch):
    monkeypatch.setenv("FIPM_NETWORK_CACHE_TTL_SECONDS", "0")
    get_settings.cache_clear()
    try:
        client.get("/api/network/fip-communities")
        assert communities_seam["n"] == 1
        client.get("/api/network/fip-communities")
        assert communities_seam["n"] == 2
    finally:
        get_settings.cache_clear()


def test_upstream_failure_warm_cache_serves_stale(client, monkeypatch):
    calls = {"n": 0}

    def flaky_get_grlc(settings, artifact_code, query_name):
        calls["n"] += 1
        if calls["n"] == 1:
            return COMMUNITIES_FIXTURE
        raise network.NetworkError("network_unavailable", 502)

    monkeypatch.setattr(network, "_get_grlc", flaky_get_grlc)
    monkeypatch.setenv("FIPM_NETWORK_CACHE_TTL_SECONDS", "0")
    get_settings.cache_clear()
    try:
        r1 = client.get("/api/network/fip-communities")
        assert r1.status_code == 200
        assert "stale" not in r1.json()

        r2 = client.get("/api/network/fip-communities")
        assert r2.status_code == 200
        assert r2.json()["stale"] is True
    finally:
        get_settings.cache_clear()


def test_upstream_failure_cold_cache_is_502(client, monkeypatch):
    def always_fails(settings, artifact_code, query_name):
        raise network.NetworkError("network_unavailable", 502)

    monkeypatch.setattr(network, "_get_grlc", always_fails)
    r = client.get("/api/network/fip-communities")
    assert r.status_code == 502
    assert r.json()["detail"] == "network_unavailable"


def test_network_disabled_returns_503_on_all_three_endpoints(client, monkeypatch):
    monkeypatch.setenv("FIPM_NETWORK_ENABLED", "false")
    get_settings.cache_clear()
    try:
        r1 = client.get("/api/network/fip-communities")
        assert r1.status_code == 503
        assert r1.json()["detail"] == "network_disabled"

        encoded_community_iri = (
            "http%3A%2F%2Fpurl.org%2Fnp%2F"
            "RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg%23PARCToxicology"
        )
        r2 = client.get(f"/api/network/fips/{encoded_community_iri}")
        assert r2.status_code == 503
        assert r2.json()["detail"] == "network_disabled"

        r3 = client.get("/api/network/fers?q=orcid")
        assert r3.status_code == 503
        assert r3.json()["detail"] == "network_disabled"

        health = client.get("/api/health")
        assert health.json()["networkEnabled"] is False
    finally:
        get_settings.cache_clear()
