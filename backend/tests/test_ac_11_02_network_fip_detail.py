"""spec 11-nanopub-network.md §3.3, builder brief A tests 8-14:
`GET /api/network/fips/{communityIri}`.

Uses the real PARC Toxicology fixtures recorded 2026-09-10
(tests/fixtures/network/parc-{fips,declarations,resources}.json)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest

from fipm import network
from fipm.models import Fer
from fipm.rdf import (
    KNOWN_QUESTION_INDIVIDUALS_ORDER,
    _question_individual_local,
    question_id_from_individual,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "network"
PARC_FIPS = json.loads((FIXTURES_DIR / "parc-fips.json").read_text())
PARC_DECLARATIONS = json.loads((FIXTURES_DIR / "parc-declarations.json").read_text())
PARC_RESOURCES = json.loads((FIXTURES_DIR / "parc-resources.json").read_text())
COMMUNITIES_FIXTURE = json.loads((FIXTURES_DIR / "fip-communities.json").read_text())

PARC_COMMUNITY_IRI = (
    "http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology"
)
PARC_FIP_TYPE_REPO_PATH = f"type/{network.FIP_TYPE_REPO}"
ENCODED_COMMUNITY_IRI = quote(PARC_COMMUNITY_IRI, safe="")


@pytest.fixture()
def parc_seam(monkeypatch):
    """Serves Q1/Q2/Q3 from the recorded fixtures, keyed by repo (matching
    how fipm.network calls _post_sparql); asserts each query substitution
    happened as expected so a broken substitution fails the test that
    exercises it, not a downstream one."""

    def fake_post_sparql(settings, repo, query):
        if repo == PARC_FIP_TYPE_REPO_PATH:
            assert f"<{PARC_COMMUNITY_IRI}>" in query
            return PARC_FIPS
        if repo == "full" and "npx:includesElement" in query:
            assert "np:hasAssertion" in query
            return PARC_DECLARATIONS
        if repo == "full" and "fip:FAIR-Enabling-Resource" in query:
            return PARC_RESOURCES
        raise AssertionError(f"unexpected repo/query: {repo}")

    def fake_get_grlc(settings, artifact_code, query_name):
        assert artifact_code == network.Q0_ARTIFACT_CODE
        assert query_name == network.Q0_QUERY_NAME
        return COMMUNITIES_FIXTURE

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)
    monkeypatch.setattr(network, "_get_grlc", fake_get_grlc)


def test_get_network_fip_all_21_questions_in_order(client, parc_seam):
    r = client.get(f"/api/network/fips/{ENCODED_COMMUNITY_IRI}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert len(body["questions"]) == 21
    assert [q["questionId"] for q in body["questions"]] == [
        question_id_from_individual(f"https://w3id.org/fair/fip/terms/FIP-Question-{local}")
        for local in KNOWN_QUESTION_INDIVIDUALS_ORDER
    ]

    f1_md = next(q for q in body["questions"] if q["questionId"] == "F1-metadata")
    assert len(f1_md["declarations"]) > 0
    current_decl = next(d for d in f1_md["declarations"] if d["status"] == "current")
    assert current_decl["resource"]["label"]


def test_fsr_declarations_land_in_unmapped_only(client, parc_seam):
    r = client.get(f"/api/network/fips/{ENCODED_COMMUNITY_IRI}")
    body = r.json()

    unmapped_iris = {entry["questionIri"] for entry in body["unmapped"]}
    assert all("FIP-S-Question" in iri for iri in unmapped_iris)
    assert len(unmapped_iris) > 0

    mapped_question_iris = {q["questionIri"] for q in body["questions"]}
    assert mapped_question_iris.isdisjoint(unmapped_iris)

    unmapped_decl_count = sum(len(entry["declarations"]) for entry in body["unmapped"])
    assert unmapped_decl_count > 0


def test_multi_type_resource_prefers_question_principle_type(client, parc_seam):
    """The real ORCID resource under F1-MD carries both Identifier-service
    (principle F1) and Communication-protocol (principle A1.1) -- F1-MD's
    own principle is F1, so ferTypeKey must resolve to identifier-service."""
    r = client.get(f"/api/network/fips/{ENCODED_COMMUNITY_IRI}")
    body = r.json()
    f1_md = next(q for q in body["questions"] if q["questionId"] == "F1-metadata")
    orcid_decls = [
        d
        for d in f1_md["declarations"]
        if d["resource"] and d["resource"]["iri"].endswith("#ORCID")
    ]
    assert orcid_decls, "fixture no longer references the ORCID resource under F1-MD"
    assert orcid_decls[0]["resource"]["ferTypeKey"] == "identifier-service"


def test_in_catalogue_homepage_match_and_no_match(client, parc_seam, db_session):
    """MIT (skos:exactMatch https://spdx.org/licenses/MIT.html) is declared
    under R1.1-metadata/R1.1-data -- seed a Fer row with that homepage and
    confirm matchedBy == "homepage"; a resource with no seeded match (e.g.
    ORCID, left unseeded here) gets inCatalogue: null. Rule 1 (Fer.id == the
    resource's own IRI) outranks rule 2 (homepage), so this removes any row
    a previous test in this shared-DB session may already hold for the raw
    MIT resource IRI or this homepage, independently of run order."""
    db_session.query(Fer).filter(
        (Fer.id == "http://purl.org/np/RA24ysQcpWDzK6wHANkG_3F1HiTbgOO4ULjYxjaXDi8C4#MIT")
        | (Fer.homepage == "https://spdx.org/licenses/MIT.html")
    ).delete()
    db_session.commit()
    db_session.add(
        Fer(
            id="https://example.org/test-mit-license",
            label={"en": "MIT License"},
            label_search="mit license",
            type="data-usage-license",
            homepage="https://spdx.org/licenses/MIT.html",
            source="seed",
        )
    )
    db_session.commit()

    r = client.get(f"/api/network/fips/{ENCODED_COMMUNITY_IRI}")
    body = r.json()

    r11_md = next(q for q in body["questions"] if q["questionId"] == "R1.1-metadata")
    mit_decls = [
        d for d in r11_md["declarations"] if d["resource"] and d["resource"]["iri"].endswith("#MIT")
    ]
    assert mit_decls, "fixture no longer references the MIT resource under R1.1-metadata"
    assert mit_decls[0]["resource"]["inCatalogue"] == {
        "ferId": "https://example.org/test-mit-license",
        "matchedBy": "homepage",
    }

    f1_md = next(q for q in body["questions"] if q["questionId"] == "F1-metadata")
    orcid_decls = [
        d
        for d in f1_md["declarations"]
        if d["resource"] and d["resource"]["iri"].endswith("#ORCID")
    ]
    assert orcid_decls[0]["resource"]["inCatalogue"] is None


def test_other_versions_excludes_newest(client, parc_seam):
    r = client.get(f"/api/network/fips/{ENCODED_COMMUNITY_IRI}")
    body = r.json()
    newest_iri = body["fip"]["nanopubIri"]
    other_iris = {v["nanopubIri"] for v in body["fip"]["otherVersions"]}
    assert newest_iri not in other_iris
    assert len(other_iris) == 3  # 4 total FIP versions in the fixture, newest excluded


def test_invalid_community_iri_400_and_seam_never_called(client, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("the seam must never be called for an invalid community IRI")

    monkeypatch.setattr(network, "_post_sparql", fail_if_called)
    monkeypatch.setattr(network, "_get_grlc", fail_if_called)

    r = client.get("/api/network/fips/" + quote("http://example.org/x>evil", safe=""))
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_community_iri"


@pytest.mark.parametrize(
    "local",
    KNOWN_QUESTION_INDIVIDUALS_ORDER,
)
def test_question_id_from_individual_is_exact_inverse(local):
    iri = f"https://w3id.org/fair/fip/terms/FIP-Question-{local}"
    question_id = question_id_from_individual(iri)
    assert question_id is not None
    assert _question_individual_local(question_id) == local


def test_question_id_from_individual_rejects_fsr_and_unknown():
    fsr_iri = "https://w3id.org/fair/fip/terms/FIP-S-Question-F1-Persistency-Policy"
    assert question_id_from_individual(fsr_iri) is None
    assert question_id_from_individual("https://example.org/x") is None
