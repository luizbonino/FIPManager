"""spec 11-nanopub-network.md §3.6/§4, builder brief A tests 29-36:
`POST /api/fips/from-network` and the `fips.network_origin` column."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from fipm import network
from fipm.config import get_settings
from fipm.models import Fer, Fip
from fipm.rdf import PROV, fip_graph

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "network"
PARC_FIPS = json.loads((FIXTURES_DIR / "parc-fips.json").read_text())
PARC_DECLARATIONS = json.loads((FIXTURES_DIR / "parc-declarations.json").read_text())
PARC_RESOURCES = json.loads((FIXTURES_DIR / "parc-resources.json").read_text())
COMMUNITIES_FIXTURE = json.loads((FIXTURES_DIR / "fip-communities.json").read_text())

PARC_COMMUNITY_IRI = (
    "http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology"
)
PARC_FIP_TYPE_REPO_PATH = f"type/{network.FIP_TYPE_REPO}"


@pytest.fixture()
def parc_seam(monkeypatch):
    def fake_post_sparql(settings, repo, query):
        if repo == PARC_FIP_TYPE_REPO_PATH:
            return PARC_FIPS
        if repo == "full" and "npx:includesElement" in query:
            return PARC_DECLARATIONS
        if repo == "full" and "fip:FAIR-Enabling-Resource" in query:
            return PARC_RESOURCES
        raise AssertionError(f"unexpected repo/query: {repo}")

    def fake_get_grlc(settings, artifact_code, query_name):
        return COMMUNITIES_FIXTURE

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)
    monkeypatch.setattr(network, "_get_grlc", fake_get_grlc)


def test_from_network_creates_fip_with_mapped_declarations(client, parc_seam):
    r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 201, r.text
    body = r.json()

    fip = body["fip"]
    assert fip["questionnaireId"] == "gofair-fip-mini"
    answered_qids = {a["questionId"] for a in fip["answers"]}
    assert answered_qids  # at least one mapped question got an answer

    all_declarations = [d for a in fip["answers"] for d in a["declarations"]]
    with_fer_id = [d for d in all_declarations if d.get("ferId")]
    assert body["imported"]["fersCreated"] + body["imported"]["fersMatched"] == len(with_fer_id)
    assert body["imported"]["declarations"] == len(all_declarations)
    assert isinstance(body["skipped"], list)


_DATACITE_RESOURCE_IRI = (
    "http://purl.org/np/RAko0U2Q8boW-drM8t11DcbX6Ixu2mcSQf-2BrM07geIQ#datacite_metadata_scheme"
)
_DATACITE_HOMEPAGE = "https://schema.datacite.org/"


def test_seed_fer_matched_by_homepage_reuses_seed_id_no_new_row(client, parc_seam, db_session):
    """The DataCite Metadata Scheme resource (skos:exactMatch
    https://schema.datacite.org/, declared under F2) matches a seeded
    catalogue row by homepage. Rule 1 (Fer.id == the resource's own IRI)
    outranks rule 2 (homepage), so this test first removes any row a
    *previous* test in this shared-DB session may already have created for
    the raw resource IRI or for this same homepage (e.g. another test's own
    seed row, or a prior `from-network` call with no seed row at all) --
    otherwise that row would win the match instead of the one this test
    seeds, independently of test execution order."""
    db_session.query(Fer).filter(
        (Fer.id == _DATACITE_RESOURCE_IRI) | (Fer.homepage == _DATACITE_HOMEPAGE)
    ).delete()
    db_session.commit()
    db_session.add(
        Fer(
            id="https://example.org/seed-datacite",
            label={"en": "DataCite Metadata Schema"},
            label_search="datacite metadata schema",
            type="metadata-schema",
            homepage=_DATACITE_HOMEPAGE,
            source="seed",
        )
    )
    db_session.commit()

    r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 201, r.text
    body = r.json()

    f2 = next((a for a in body["fip"]["answers"] if a["questionId"] == "F2"), None)
    assert f2 is not None, "PARC fixture no longer answers F2"
    fer_ids = {d["ferId"] for d in f2["declarations"] if d.get("ferId")}
    assert "https://example.org/seed-datacite" in fer_ids
    assert _DATACITE_RESOURCE_IRI not in fer_ids

    # The seed row was reused; only genuinely-unmatched resources create rows.
    new_row = db_session.get(Fer, "https://example.org/seed-datacite")
    assert new_row is not None
    assert new_row.source == "seed"  # untouched, not overwritten by the import


def test_unmatched_resource_creates_one_network_fer_row_idempotently(client, parc_seam, db_session):
    r1 = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r1.status_code == 201, r1.text
    body1 = r1.json()

    orcid_answer = next(
        (a for a in body1["fip"]["answers"] if a["questionId"] == "F1-metadata"), None
    )
    assert orcid_answer is not None
    orcid_decl = next(
        (d for d in orcid_answer["declarations"] if d.get("ferId", "").endswith("#ORCID")), None
    )
    assert orcid_decl is not None, "PARC fixture no longer declares ORCID under F1-metadata"
    fer_id = orcid_decl["ferId"]

    row = db_session.get(Fer, fer_id)
    assert row is not None
    assert row.source == "network"
    assert row.id == fer_id  # the nanopub-fragment IRI verbatim

    count_after_first = db_session.query(Fer).filter(Fer.id == fer_id).count()
    assert count_after_first == 1

    r2 = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r2.status_code == 201, r2.text
    count_after_second = db_session.query(Fer).filter(Fer.id == fer_id).count()
    assert count_after_second == 1  # no duplicate row


def test_network_fer_row_visible_to_anonymous_fer_listing(client, parc_seam):
    r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 201, r.text

    listing = client.get("/api/fers?source=network&limit=200")
    assert listing.status_code == 200
    assert listing.json()["total"] > 0


def test_network_origin_set_and_rdf_emits_was_derived_from(client, parc_seam, db_session, settings):
    r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 201, r.text
    body = r.json()
    fip_id = body["fip"]["id"]

    assert body["fip"]["networkOrigin"]["communityIri"] == PARC_COMMUNITY_IRI
    assert body["fip"]["networkOrigin"]["fipNanopubIri"]
    assert body["fip"]["networkOrigin"]["fetchedAt"]

    fip_row = db_session.get(Fip, fip_id)
    assert fip_row.network_origin["communityIri"] == PARC_COMMUNITY_IRI

    g = fip_graph(db_session, fip_row, settings)
    from rdflib import URIRef

    from fipm.exporters import fip_url

    fip_iri = URIRef(fip_url(fip_row, settings))
    assert (
        fip_iri,
        PROV.wasDerivedFrom,
        URIRef(fip_row.network_origin["fipNanopubIri"]),
    ) in g


def test_export_json_roundtrips_network_origin_through_import(client, parc_seam):
    owner = client
    owner.post(
        "/api/auth/register",
        json={
            "email": "ac1104-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "Owner",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    r = owner.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 201, r.text
    fip_id = r.json()["fip"]["id"]

    export_doc = owner.get(f"/api/fips/{fip_id}/export.json").json()
    assert export_doc["fip"]["networkOrigin"]["communityIri"] == PARC_COMMUNITY_IRI

    imported = owner.post("/api/fips/import", json=export_doc)
    assert imported.status_code == 201, imported.text
    assert imported.json()["networkOrigin"] == export_doc["fip"]["networkOrigin"]


def test_anonymous_fips_disabled_returns_403(client, parc_seam, monkeypatch):
    monkeypatch.setenv("FIPM_ANONYMOUS_FIPS", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
        assert r.status_code == 403
        assert r.json()["detail"] == "anonymous_fips_disabled"
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Review finding 10: the authorization ladder runs before any network call
# or FER write. `FIPM_ANONYMOUS_FIPS=false` with NO `parc_seam` fixture --
# the autouse `_guard_network_calls` fixture (conftest.py) makes
# `_post_sparql`/`_get_grlc` raise `AssertionError` if called at all, so if
# the endpoint reached the network before rejecting the caller, this test
# would see a 500, not the expected 403.
# ---------------------------------------------------------------------------


def test_anonymous_fips_disabled_never_touches_the_network(client, monkeypatch):
    monkeypatch.setenv("FIPM_ANONYMOUS_FIPS", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
        assert r.status_code == 403
        assert r.json()["detail"] == "anonymous_fips_disabled"
    finally:
        get_settings.cache_clear()


def test_private_visibility_with_no_account_never_touches_the_network(client):
    """No `parc_seam` fixture here either -- private_requires_account must
    be rejected before the network seam is ever called."""
    r = client.post(
        "/api/fips/from-network",
        json={"communityIri": PARC_COMMUNITY_IRI, "visibility": "private"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "private_requires_account"


def test_anonymous_rate_limit_returns_429_before_touching_the_network(client, monkeypatch):
    """Same tight-cap pattern as test_standalone_fips.py's
    `small_anonymous_fip_rate_limit`: two cheap `POST /api/fips` calls
    exhaust a limit of 2, then the third call -- to `/fips/from-network`,
    with no `parc_seam` fixture -- must 429 without ever reaching the
    network seam."""
    import fipm.auth as auth_module

    monkeypatch.setattr(auth_module, "ANONYMOUS_FIP_LIMIT_PER_IP", 2)
    qref = {"id": "test-km", "version": "1.0.0"}
    first = client.post("/api/fips", json={"questionnaireRef": qref})
    assert first.status_code == 201, first.text
    second = client.post("/api/fips", json={"questionnaireRef": qref})
    assert second.status_code == 201, second.text

    r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 429
    assert r.json()["detail"] == "rate_limited"


def test_wrong_join_code_returns_403_never_touches_the_network(client):
    owner = client
    _register_facilitator(owner, "ac1104-wrongjoin@example.com")
    session = owner.post(
        "/api/sessions",
        json={
            "title": "Wrong join code session",
            "defaultLanguage": "en",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        },
    ).json()

    r = client.post(
        "/api/fips/from-network",
        json={
            "communityIri": PARC_COMMUNITY_IRI,
            "sessionId": session["id"],
            "joinCode": "WRONGX",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "invalid_join_code"


def test_network_disabled_returns_503_before_any_authorization_check(client, monkeypatch):
    monkeypatch.setenv("FIPM_NETWORK_ENABLED", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
        assert r.status_code == 503
        assert r.json()["detail"] == "network_disabled"
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Review finding 3: everything the network hands back is validated before
# it can create a `fers` row or land in `answers`.
# ---------------------------------------------------------------------------


def test_malicious_resource_iri_is_skipped_no_fer_row_and_fip_still_patches(
    client, monkeypatch, db_session
):
    doctored = copy.deepcopy(PARC_DECLARATIONS)
    target = doctored["results"]["bindings"][0]
    target["resource"]["value"] = "javascript:alert(1)//x"

    def fake_post_sparql(settings, repo, query):
        if repo == PARC_FIP_TYPE_REPO_PATH:
            return PARC_FIPS
        if repo == "full" and "npx:includesElement" in query:
            return doctored
        if repo == "full" and "fip:FAIR-Enabling-Resource" in query:
            return PARC_RESOURCES
        raise AssertionError(f"unexpected repo/query: {repo}")

    def fake_get_grlc(settings, artifact_code, query_name):
        return COMMUNITIES_FIXTURE

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)
    monkeypatch.setattr(network, "_get_grlc", fake_get_grlc)

    r = client.post("/api/fips/from-network", json={"communityIri": PARC_COMMUNITY_IRI})
    assert r.status_code == 201, r.text
    body = r.json()

    assert db_session.get(Fer, "javascript:alert(1)//x") is None
    assert any(s.get("reason") == "invalid_resource_iri" for s in body["skipped"])
    for answer in body["fip"]["answers"]:
        for decl in answer["declarations"]:
            assert decl.get("ferId") != "javascript:alert(1)//x"

    fip_id = body["fip"]["id"]
    edit_token = body.get("editToken")
    headers = {"X-Edit-Token": edit_token} if edit_token else {}
    patched = client.patch(f"/api/fips/{fip_id}", json={"language": "en"}, headers=headers)
    assert patched.status_code == 200, patched.text


# ---------------------------------------------------------------------------
# Review finding 8: the requested questionnaireRef (session-scoped) is
# honoured when given and allowed; declarations for a question the target
# model doesn't have are skipped with reason question_not_in_model.
# ---------------------------------------------------------------------------


def _register_facilitator(client, email: str) -> dict:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_from_network_session_honours_requested_ref_and_skips_unmapped_questions(
    client, client_factory, parc_seam
):
    """`nanopub-test-km` (used by test_ac_11_03) only has F1-metadata, F2
    and A2 -- far fewer than the 21 canonical GO FAIR ids -- so any PARC
    declaration under a question outside that set (e.g. A1.1-data, which
    the PARC fixture does declare) must be skipped with reason
    question_not_in_model rather than silently answered."""
    facilitator = client_factory()
    _register_facilitator(facilitator, "ac1104-facilitator@example.com")
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "Multi-area session",
            "defaultLanguage": "en",
            "questionnaireRefs": [
                {"id": "test-km", "version": "1.0.0", "label": {"en": "Full"}},
                {"id": "nanopub-test-km", "version": "1.0.0", "label": {"en": "Partial"}},
            ],
        },
    ).json()

    r = client.post(
        "/api/fips/from-network",
        json={
            "communityIri": PARC_COMMUNITY_IRI,
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "questionnaireRef": {"id": "nanopub-test-km", "version": "1.0.0"},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["fip"]["questionnaireId"] == "nanopub-test-km"
    answered_qids = {a["questionId"] for a in body["fip"]["answers"]}
    assert "A1.1-data" not in answered_qids  # not one of nanopub-test-km's 3 questions

    assert any(
        s.get("questionId") == "A1.1-data" and s.get("reason") == "question_not_in_model"
        for s in body["skipped"]
    ), body["skipped"]


def test_from_network_session_with_no_ref_falls_back_to_first_ref(
    client, client_factory, parc_seam
):
    facilitator = client_factory()
    _register_facilitator(facilitator, "ac1104-facilitator2@example.com")
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "Multi-area session 2",
            "defaultLanguage": "en",
            "questionnaireRefs": [
                {"id": "test-km", "version": "1.0.0", "label": {"en": "First"}},
                {"id": "nanopub-test-km", "version": "1.0.0", "label": {"en": "Second"}},
            ],
        },
    ).json()

    r = client.post(
        "/api/fips/from-network",
        json={
            "communityIri": PARC_COMMUNITY_IRI,
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["fip"]["questionnaireId"] == "test-km"


def test_from_network_session_ref_not_in_session_is_400(client, client_factory, parc_seam):
    facilitator = client_factory()
    _register_facilitator(facilitator, "ac1104-facilitator3@example.com")
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "Single-ref session",
            "defaultLanguage": "en",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        },
    ).json()

    r = client.post(
        "/api/fips/from-network",
        json={
            "communityIri": PARC_COMMUNITY_IRI,
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "questionnaireRef": {"id": "nanopub-test-km", "version": "1.0.0"},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "questionnaire_ref_mismatch"


# ---------------------------------------------------------------------------
# Test 36: schema 6 -> 7 upgrade.
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
IMPORT_FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"

_V6_SCHEMA_SQL = """
CREATE TABLE users (
    id VARCHAR(26) PRIMARY KEY,
    email VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    language VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    must_change_password BOOLEAN NOT NULL DEFAULT 0,
    privacy_accepted_version VARCHAR,
    email_verified_at DATETIME
);
CREATE UNIQUE INDEX ix_users_email ON users(email);
CREATE TABLE knowledge_models (
    id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    owner_id VARCHAR,
    visibility VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    license VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT 0,
    title JSON NOT NULL,
    description JSON NOT NULL,
    changelog JSON NOT NULL,
    content JSON NOT NULL,
    content_sha256 VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (id, version)
);
CREATE TABLE workshop_sessions (
    id VARCHAR NOT NULL PRIMARY KEY,
    join_code VARCHAR(6) NOT NULL,
    owner_id VARCHAR,
    questionnaire_id VARCHAR NOT NULL,
    questionnaire_version VARCHAR NOT NULL,
    questionnaire_refs JSON,
    default_language VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
);
CREATE UNIQUE INDEX ix_sessions_join_code ON workshop_sessions(join_code);
CREATE TABLE fips (
    id VARCHAR NOT NULL PRIMARY KEY,
    owner_id VARCHAR,
    session_id VARCHAR,
    edit_token_hash VARCHAR(64),
    visibility VARCHAR NOT NULL,
    questionnaire_id VARCHAR NOT NULL,
    questionnaire_version VARCHAR NOT NULL,
    title VARCHAR,
    community JSON,
    related_dmps JSON,
    answers JSON NOT NULL,
    language VARCHAR NOT NULL,
    license VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    migrated_from JSON,
    orphaned_answers JSON
);
CREATE TABLE schema_version (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at DATETIME
);
INSERT INTO schema_version (id, version, applied_at)
    VALUES (1, 6, '2026-01-01T00:00:00+00:00');
INSERT INTO fips
    (id, owner_id, session_id, edit_token_hash, visibility, questionnaire_id, questionnaire_version,
     title, community, related_dmps, answers, language, license, created_at, updated_at,
     migrated_from, orphaned_answers)
    VALUES (
        'preexisting-v6-fip', NULL, NULL, 'sometokenhash', 'link', 'test-km', '1.0.0',
        'A pre-v7 FIP', NULL, '[]', '[]', 'en', 'CC0-1.0',
        '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', NULL, '[]'
    );
"""


def _build_v6_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_V6_SCHEMA_SQL)
    conn.commit()
    conn.close()


def _run_import(db_path: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["FIPM_DB_PATH"] = db_path
    env["FIPM_DATA_DIR"] = str(IMPORT_FIXTURES_DIR)
    env["FIPM_STATIC_DIR"] = str(IMPORT_FIXTURES_DIR / "no-such-static-dir")
    env.pop("FIPM_ADMIN_EMAIL", None)
    env.pop("FIPM_ADMIN_PASSWORD", None)
    return subprocess.run(
        [sys.executable, "-m", "fipm", "import-data"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_v6_db_upgrades_to_v7_adds_network_origin_nullable(tmp_path):
    db_path = str(tmp_path / "v6_upgrade.db")
    _build_v6_db(db_path)

    r1 = _run_import(db_path)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(fips)")}
    assert "network_origin" in cols

    row = conn.execute(
        "SELECT title, network_origin FROM fips WHERE id = 'preexisting-v6-fip'"
    ).fetchone()
    assert row is not None
    title, network_origin = row
    assert title == "A pre-v7 FIP"
    assert network_origin is None

    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
    from fipm.db import SCHEMA_VERSION

    assert version == SCHEMA_VERSION
    conn.close()

    r2 = _run_import(db_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    conn2 = sqlite3.connect(db_path)
    cols2 = {row[1] for row in conn2.execute("PRAGMA table_info(fips)")}
    assert cols2 == cols  # idempotent
    conn2.close()
