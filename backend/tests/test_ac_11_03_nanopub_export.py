"""spec 11-nanopub-network.md §2, builder brief A tests 15-28: the unsigned
nanopublication bundle (`fipm.nanopub_export.build_bundle`) and its three
`GET /api/fips/{id}/export/nanopubs*` endpoints.

Uses `tests/fixtures/knowledge-models/nanopub-test-km-1.0.0.json`: three
GO FAIR mini ids (F1-metadata, F2, A2 -- each mappable to a
`fip:FIP-Question-*` individual) plus one forked id, `confoa-omics-1`, with
no ontology counterpart at all (the §2.5 skip case). FIPs are inserted
directly into the DB (like test_rdf_export.py's `_insert_fip`), bypassing
the API's pydantic validation, so a declaration's exact shape is fully
under the test's control."""

from __future__ import annotations

import re
import zipfile
from datetime import UTC, datetime
from io import BytesIO

import pytest
from rdflib import Dataset, Namespace, URIRef

from fipm.db import SessionLocal
from fipm.exporters import fip_url
from fipm.ids import short_id
from fipm.models import Fip, User
from fipm.nanopub_export import NanopubBundleError, build_bundle

KM_ID = "nanopub-test-km"
KM_VERSION = "1.0.0"


@pytest.fixture(autouse=True)
def _ensure_tables_exist(app):
    """The session-scoped `app` fixture is what actually runs `init_db()`
    (via `run_import()`); several tests here use `db_session` directly with
    no `client`, so this file needs `app` pulled in explicitly rather than
    relying on file/test execution order across the whole suite."""
    yield


NP = Namespace("http://www.nanopub.org/nschema#")

_HEAD_METADATA_QUERY = """
PREFIX np: <http://www.nanopub.org/nschema#>
SELECT ?nanopub ?assertion ?provenance ?pubinfo WHERE {
  GRAPH ?head {
    ?nanopub a np:Nanopublication ;
      np:hasAssertion ?assertion ;
      np:hasProvenance ?provenance ;
      np:hasPublicationInfo ?pubinfo .
  }
}
"""


def _insert_fip(db_session, settings, **overrides):
    defaults = dict(
        owner_id=None,
        session_id=None,
        edit_token_hash=None,
        visibility="public",
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        title=None,
        community={"name": "Test group", "description": "A test community", "domain": None},
        related_dmps=[],
        answers=[],
        language="en",
        license="CC0-1.0",
    )
    defaults.update(overrides)
    fip = Fip(id=short_id(settings.id_prefix), **defaults)
    db_session.add(fip)
    db_session.commit()
    db_session.refresh(fip)
    return fip


def _parse_all(bundle) -> dict[str, Dataset]:
    parsed = {}
    for path, text in bundle.files:
        ds = Dataset()
        ds.parse(data=text, format="trig")
        parsed[path] = ds
    return parsed


def _named_graphs(ds: Dataset) -> list:
    """Contexts that actually carry a triple -- excludes rdflib's own
    always-present, always-empty default-graph context."""
    return [c for c in ds.graphs() if len(c) > 0]


def _all_text(bundle) -> str:
    return "\n".join(text for _path, text in bundle.files)


# ---------------------------------------------------------------------------
# Test 15/16/17/18: shape.
# ---------------------------------------------------------------------------


@pytest.fixture()
def three_decl_fip(db_session, settings):
    return _insert_fip(
        db_session,
        settings,
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"ferId": "https://www.doi.org/", "status": "current"}],
            },
            {
                "questionId": "F2",
                "declarations": [{"ferFreeText": "A free-text schema", "status": "current"}],
            },
            {
                "questionId": "A2",
                "declarations": [{"ferFreeText": "A preservation policy", "status": "current"}],
            },
        ],
    )


def test_zip_has_6_entries_and_signing_order_filenames(db_session, settings, three_decl_fip):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    assert bundle.index["counts"]["nanopubs"] == 6
    assert bundle.index["counts"]["declarations"] == 3
    assert bundle.index["counts"]["skipped"] == 0

    zf = zipfile.ZipFile(BytesIO(bundle.zip_bytes()))
    names = zf.namelist()
    root = f"{three_decl_fip.id}-nanopubs"
    assert f"{root}/index.json" in names
    assert f"{root}/MANIFEST.md" in names
    np_names = sorted(n for n in names if f"{root}/np/" in n)
    assert len(np_names) == 6
    # Lexicographic file order == signing order (0001..0006).
    assert np_names == sorted(np_names)
    assert np_names[0].endswith("0001-community.trig")
    assert np_names[-1].endswith("0006-fip.trig")


def test_every_trig_satisfies_extract_np_metadata_shape(db_session, settings, three_decl_fip):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    parsed = _parse_all(bundle)
    for path, ds in parsed.items():
        named = _named_graphs(ds)
        assert len(named) == 4, f"{path} has {len(named)} non-empty named graphs, want 4"
        rows = list(ds.query(_HEAD_METADATA_QUERY))
        assert len(rows) == 1, f"{path} does not satisfy extract_np_metadata's Head-graph shape"


def test_no_signature_or_nt_triples_anywhere(db_session, settings, three_decl_fip):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    text = _all_text(bundle)
    for forbidden in (
        "npx:hasSignature",
        "npx:hasPublicKey",
        "npx:hasAlgorithm",
        "npx:hasSignatureTarget",
        "http://purl.org/nanopub/x/hasSignature",
        "nt:wasCreatedFromTemplate",
        "http://purl.org/nanopub/nt#",
        # Builder brief / review finding 13: the Wizard never authors
        # npx:hasNanopubType either (spec §0.2) -- it lives in the
        # registry's npa:graph, derived from the assertion's rdf:type.
        "npx:hasNanopubType",
        "http://purl.org/nanopub/x/hasNanopubType",
    ):
        assert forbidden not in text, f"found forbidden token {forbidden!r} in the bundle"


def test_every_temp_iri_uses_the_bundles_own_base_and_rewrites_are_internally_consistent(
    db_session, settings, three_decl_fip
):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    text = _all_text(bundle)
    own_prefix = f"http://purl.org/nanopub/temp/fipm/{three_decl_fip.id}/"
    for match in re.finditer(r"http://purl\.org/nanopub/temp/fipm/[^\s<>]+", text):
        assert match.group(0).startswith(own_prefix), match.group(0)

    ns_by_n = {entry["n"] for entry in bundle.index["nanopubs"]}
    for rewrite in bundle.index["rewrites"]:
        assert rewrite["afterSigning"] in ns_by_n
        assert rewrite["replacePrefix"].startswith(own_prefix)
        assert rewrite["inFiles"]  # only entries with a real referencedBy are emitted


# ---------------------------------------------------------------------------
# Test 19: status -> predicate mapping.
# ---------------------------------------------------------------------------


def test_status_predicates(db_session, settings):
    fip = _insert_fip(
        db_session,
        settings,
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [
                    {"ferId": "https://www.doi.org/", "status": "current"},
                    {
                        "ferId": "https://www.handle.net/",
                        "status": "planned-replacement",
                        "successorFerId": "https://www.doi.org/",
                    },
                    {"ferFreeText": "no choice made yet", "status": "none"},
                    {"ferFreeText": "will build one", "status": "planned-development"},
                ],
            }
        ],
    )
    bundle = build_bundle(db_session, fip, settings, datetime.now(UTC))
    by_file = dict(bundle.files)
    ns = "https://w3id.org/fair/fip/terms/"

    current_text = by_file["np/0002-decl-F1-MD-0.trig"]
    assert f"{ns}declares-current-use-of" in current_text
    assert "FIP-No-Choice-Declaration" not in current_text

    replacement_text = by_file["np/0003-decl-F1-MD-1.trig"]
    assert f"{ns}declares-planned-replacement-of" in replacement_text
    assert f"{ns}declares-planned-use-of" in replacement_text

    none_text = by_file["np/0004-decl-F1-MD-2.trig"]
    assert "FIP-No-Choice-Declaration" in none_text
    assert f"{ns}declares-" not in none_text

    dev_text = by_file["np/0005-decl-F1-MD-3.trig"]
    assert f"{ns}declares-planned-development-of" in dev_text


# ---------------------------------------------------------------------------
# Test 20: notApplicable.
# ---------------------------------------------------------------------------


def test_not_applicable_produces_no_nanopub(db_session, settings):
    fip = _insert_fip(
        db_session,
        settings,
        answers=[{"questionId": "A2", "notApplicable": True, "declarations": []}],
    )
    bundle = build_bundle(db_session, fip, settings, datetime.now(UTC))
    assert bundle.index["counts"]["declarations"] == 0
    assert bundle.index["counts"]["nanopubs"] == 3  # community + index + fip, N=0
    assert bundle.index["notRepresented"]["notApplicable"] == ["A2"]
    assert "A2" not in _all_text(bundle)


# ---------------------------------------------------------------------------
# Test 21: unmapped question id.
# ---------------------------------------------------------------------------


def test_unmapped_question_is_skipped(db_session, settings):
    fip = _insert_fip(
        db_session,
        settings,
        answers=[
            {
                "questionId": "confoa-omics-1",
                "declarations": [{"ferFreeText": "an omics resource", "status": "current"}],
            }
        ],
    )
    bundle = build_bundle(db_session, fip, settings, datetime.now(UTC))
    assert bundle.index["counts"]["declarations"] == 0
    assert bundle.index["skipped"] == [
        {"questionId": "confoa-omics-1", "declarationIndex": 0, "reason": "no_question_individual"}
    ]
    np_files = [p for p, _ in bundle.files if p.startswith("np/") and "decl" in p]
    assert np_files == []


# ---------------------------------------------------------------------------
# Test 22: dmpEvidence / relatedDmps never appear in any .trig.
# ---------------------------------------------------------------------------


def test_dmp_evidence_and_related_dmps_omitted_from_trig(db_session, settings):
    fip = _insert_fip(
        db_session,
        settings,
        related_dmps=[{"url": "https://fiodmp.fiocruz.br/plans/abc", "system": "fiodmp"}],
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [
                    {
                        "ferId": "https://www.doi.org/",
                        "status": "current",
                        "dmpEvidence": {"dmpIndex": 0, "section": "3.2", "questionRef": "q1"},
                    }
                ],
            }
        ],
    )
    bundle = build_bundle(db_session, fip, settings, datetime.now(UTC))
    text = _all_text(bundle)
    assert "fiodmp.fiocruz.br" not in text
    assert "dmp-evidence" not in text
    assert "dmp-section" not in text
    assert bundle.index["notRepresented"]["dmpEvidence"] == [
        {"questionId": "F1-metadata", "declarationIndex": 0}
    ]
    assert bundle.index["notRepresented"]["relatedDmps"] == 1


# ---------------------------------------------------------------------------
# Test 23: declaration index shape.
# ---------------------------------------------------------------------------


def test_index_nanopub_includes_element_set_and_is_index_assertion(
    db_session, settings, three_decl_fip
):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    by_path = dict(bundle.files)
    index_text = by_path["np/0005-index.trig"]

    decl_bases = {
        entry["tempNanopubIri"]
        for entry in bundle.index["nanopubs"]
        if entry["role"] == "declaration"
    }
    for base in decl_bases:
        assert f"<{base}>" in index_text
    assert "http://purl.org/nanopub/x/IndexAssertion" in index_text


# ---------------------------------------------------------------------------
# Test 24: FIP nanopub shape.
# ---------------------------------------------------------------------------


def test_fip_nanopub_points_at_index_and_community(db_session, settings, three_decl_fip):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    by_path = dict(bundle.files)
    fip_text = by_path["np/0006-fip.trig"]

    community_entry = next(e for e in bundle.index["nanopubs"] if e["role"] == "community")
    index_entry = next(e for e in bundle.index["nanopubs"] if e["role"] == "index")

    assert f"<{index_entry['tempNanopubIri']}>" in fip_text
    assert f"<{community_entry['conceptIri']}>" in fip_text


# ---------------------------------------------------------------------------
# Test 25: private FIP -> no prov:wasDerivedFrom to the FIP URL.
# ---------------------------------------------------------------------------


def test_private_fip_omits_was_derived_from(db_session, settings, three_decl_fip):
    three_decl_fip.visibility = "private"
    three_decl_fip.owner_id = None  # irrelevant to the bundle logic itself
    db_session.commit()
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    url = fip_url(three_decl_fip, settings)
    assert url not in _all_text(bundle)


# ---------------------------------------------------------------------------
# Test 26: preview.trig endpoint.
# ---------------------------------------------------------------------------


def test_preview_trig_defaults_to_fip_nanopub_and_404_out_of_range(client, three_decl_fip):
    r_default = client.get(f"/api/fips/{three_decl_fip.id}/export/nanopubs/preview.trig")
    assert r_default.status_code == 200
    assert r_default.headers["content-type"].startswith("application/trig")
    assert "FAIR-Implementation-Profile" in r_default.text

    r_n1 = client.get(f"/api/fips/{three_decl_fip.id}/export/nanopubs/preview.trig?n=1")
    assert r_n1.status_code == 200
    assert "FAIR-Implementation-Community" in r_n1.text

    r_missing = client.get(f"/api/fips/{three_decl_fip.id}/export/nanopubs/preview.trig?n=999")
    assert r_missing.status_code == 404


# ---------------------------------------------------------------------------
# Test 27: authorization identical to export.ttl.
# ---------------------------------------------------------------------------


def _register(client, email, display_name="U"):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": display_name,
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _promote_to_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()


def test_authorization_matches_export_ttl_across_visibility_and_caller(client, client_factory):
    qref = {"id": KM_ID, "version": KM_VERSION}

    # 1) anonymous caller, public FIP
    public_fip = client.post(
        "/api/fips", json={"questionnaireRef": qref, "visibility": "public"}
    ).json()

    # 2) anonymous caller, link FIP (standalone, with an edit token)
    link_fip = client.post(
        "/api/fips", json={"questionnaireRef": qref, "visibility": "link"}
    ).json()
    link_token = link_fip["editToken"]

    # 3) anonymous caller, private FIP (owned)
    owner = client_factory()
    _register(owner, "ac11-owner@example.com")
    private_fip = owner.post(
        "/api/fips", json={"questionnaireRef": qref, "visibility": "private"}
    ).json()

    admin_email = "ac11-admin@example.com"
    admin = client_factory()
    _register(admin, admin_email)
    _promote_to_admin(admin_email)

    combos = [
        ("anonymous+public", client, public_fip["id"], {}, 200),
        ("anonymous+link", client, link_fip["id"], {}, 200),
        ("anonymous+private", client, private_fip["id"], {}, 404),
        ("edit-token-holder", client, link_fip["id"], {"X-Edit-Token": link_token}, 200),
        ("owner", owner, private_fip["id"], {}, 200),
        ("admin", admin, private_fip["id"], {}, 200),
    ]
    for _label, caller, fip_id, headers, expected in combos:
        ttl = caller.get(f"/api/fips/{fip_id}/export.ttl", headers=headers)
        zip_resp = caller.get(f"/api/fips/{fip_id}/export/nanopubs.zip", headers=headers)
        # Review finding 13: the other two nanopub endpoints (index.json,
        # preview.trig) carry the same authorization, not just the zip.
        index_resp = caller.get(f"/api/fips/{fip_id}/export/nanopubs/index.json", headers=headers)
        preview_resp = caller.get(
            f"/api/fips/{fip_id}/export/nanopubs/preview.trig", headers=headers
        )
        assert ttl.status_code == expected, _label
        assert zip_resp.status_code == expected, _label
        assert index_resp.status_code == expected, _label
        assert preview_resp.status_code == expected, _label
        assert ttl.status_code == zip_resp.status_code == index_resp.status_code, _label
        assert ttl.status_code == preview_resp.status_code, _label


# ---------------------------------------------------------------------------
# Test 28: determinism.
# ---------------------------------------------------------------------------


def test_two_calls_with_frozen_clock_are_byte_identical(db_session, settings, three_decl_fip):
    frozen = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    bundle1 = build_bundle(db_session, three_decl_fip, settings, frozen)
    bundle2 = build_bundle(db_session, three_decl_fip, settings, frozen)
    assert bundle1.zip_bytes() == bundle2.zip_bytes()


# ---------------------------------------------------------------------------
# Review finding 1: npx:introduces subject is the nanopub itself (`this:`),
# not the pubinfo graph's own IRI.
# ---------------------------------------------------------------------------

NPX_INTRODUCES = URIRef("http://purl.org/nanopub/x/introduces")


def test_npx_introduces_subject_is_the_nanopub_not_pubinfo_graph(
    db_session, settings, three_decl_fip
):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    parsed = _parse_all(bundle)

    community_entry = next(e for e in bundle.index["nanopubs"] if e["role"] == "community")
    fip_entry = next(e for e in bundle.index["nanopubs"] if e["role"] == "fip")

    for entry in (community_entry, fip_entry):
        ds = parsed[entry["file"]]
        this = URIRef(entry["tempNanopubIri"])
        concept = URIRef(entry["conceptIri"])
        subjects = {s for s, p, _o, _ctx in ds.quads((None, NPX_INTRODUCES, None, None))}
        assert subjects == {this}, (
            f"{entry['role']}: npx:introduces subject(s) {subjects}, want {{{this}}}"
        )
        assert list(ds.quads((this, NPX_INTRODUCES, concept, None)))


# ---------------------------------------------------------------------------
# Review finding 2: IRI injection into the hand-rolled TriG serialiser.
# ---------------------------------------------------------------------------


def test_malicious_link_and_fer_id_never_reach_the_trig_and_declaration_is_skipped(
    db_session, settings
):
    malicious_link = (
        'https://evil.example/x"} evilgraph1 { <https://evil.example/s> '
        "<https://evil.example/p> <https://evil.example/o"
    )
    malicious_fer_id = (
        'https://evil.example/fer"} evilgraph2 { <https://evil.example/s2> '
        "<https://evil.example/p2> <https://evil.example/o2"
    )
    fip = _insert_fip(
        db_session,
        settings,
        community={
            "name": "Test group",
            "description": "A test community",
            "domain": None,
            "links": [malicious_link, "https://ok.example/fine"],
        },
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"ferId": malicious_fer_id, "status": "current"}],
            }
        ],
    )
    bundle = build_bundle(db_session, fip, settings, datetime.now(UTC))

    # The declaration is skipped (reason invalid_iri) -- no nanopub was ever
    # built from the malicious ferId.
    assert bundle.index["skipped"] == [
        {"questionId": "F1-metadata", "declarationIndex": 0, "reason": "invalid_iri"}
    ]
    text = _all_text(bundle)
    assert malicious_link not in text
    assert malicious_fer_id not in text
    assert "https://ok.example/fine" in text  # the safe link still gets through

    # Every .trig file still parses cleanly with rdflib, at most the 4
    # legitimate named graphs (the declaration index's own assertion graph
    # is empty and so vanishes on parse -- a pre-existing, unrelated fact,
    # not an injection) and none of them the attacker's own graph name.
    parsed = _parse_all(bundle)
    for path, ds in parsed.items():
        named = _named_graphs(ds)
        assert len(named) <= 4, f"{path} has {len(named)} named graphs, want at most 4 (injection?)"
        for g in named:
            assert "evilgraph" not in str(g.identifier), f"{path}: injected graph {g.identifier}"


def test_format_term_rejects_unsafe_iri_characters():
    from fipm.nanopub_export import _format_term, _is_safe_iriref

    for bad in (
        "https://example.org/x>evil",
        'https://example.org/x"evil',
        "https://example.org/x{evil}",
        "https://example.org/x|evil",
        "https://example.org/x^evil",
        "https://example.org/x\\evil",
        "https://example.org/x`evil",
        "https://example.org/x evil",
        "https://example.org/x\tevil",
        "https://example.org/x\x00evil",
    ):
        assert not _is_safe_iriref(bad), bad
        with pytest.raises(ValueError):
            _format_term(URIRef(bad))
    assert _is_safe_iriref("https://example.org/fine")


# ---------------------------------------------------------------------------
# Review finding 5: dct:created is second-precision, Z-suffixed, exact.
# ---------------------------------------------------------------------------


def test_dct_created_is_second_precision_utc_z_suffixed(db_session, settings, three_decl_fip):
    now_with_micros = datetime(2026, 9, 10, 12, 0, 0, 123456, tzinfo=UTC)
    bundle = build_bundle(db_session, three_decl_fip, settings, now_with_micros)
    text = _all_text(bundle)
    assert '"2026-09-10T12:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>' in text, text
    assert "123456" not in text
    assert bundle.index["generator"]["generatedAt"] == "2026-09-10T12:00:00Z"


# ---------------------------------------------------------------------------
# Review finding 6: MAX_NP_PER_INDEX guard -> 413 too_many_declarations.
# ---------------------------------------------------------------------------


def test_max_np_per_index_guard_raises_413(db_session, settings, monkeypatch):
    from fipm import nanopub_export

    monkeypatch.setattr(nanopub_export, "MAX_NP_PER_INDEX", 1)
    fip = _insert_fip(
        db_session,
        settings,
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [
                    {"ferId": "https://www.doi.org/", "status": "current"},
                    {"ferId": "https://www.handle.net/", "status": "current"},
                ],
            }
        ],
    )
    with pytest.raises(NanopubBundleError) as exc_info:
        nanopub_export.build_bundle(db_session, fip, settings, datetime.now(UTC))
    assert exc_info.value.code == "too_many_declarations"
    assert exc_info.value.status_code == 413


def test_export_endpoints_return_413_when_declaration_count_exceeds_guard(client, monkeypatch):
    from fipm import nanopub_export

    monkeypatch.setattr(nanopub_export, "MAX_NP_PER_INDEX", 1)
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "visibility": "public",
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {"ferId": "https://www.doi.org/", "status": "current"},
                        {"ferId": "https://www.handle.net/", "status": "current"},
                    ],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    for path in (
        f"/api/fips/{fip_id}/export/nanopubs.zip",
        f"/api/fips/{fip_id}/export/nanopubs/index.json",
        f"/api/fips/{fip_id}/export/nanopubs/preview.trig",
    ):
        r = client.get(path)
        assert r.status_code == 413, f"{path}: {r.status_code} {r.text}"
        assert r.json()["detail"] == "too_many_declarations"


# ---------------------------------------------------------------------------
# Review finding 7 / spec §7 Q5: an untagged rdfs:label alongside the
# language-tagged one, on both the community and FIP nanopubs.
# ---------------------------------------------------------------------------


def test_community_and_fip_labels_are_emitted_both_tagged_and_untagged(
    db_session, settings, three_decl_fip
):
    bundle = build_bundle(db_session, three_decl_fip, settings, datetime.now(UTC))
    parsed = _parse_all(bundle)

    community_entry = next(e for e in bundle.index["nanopubs"] if e["role"] == "community")
    fip_entry = next(e for e in bundle.index["nanopubs"] if e["role"] == "fip")

    from rdflib import RDFS

    for entry in (community_entry, fip_entry):
        ds = parsed[entry["file"]]
        concept = URIRef(entry["conceptIri"])
        labels = [o for _s, _p, o, _ctx in ds.quads((concept, RDFS.label, None, None))]
        tagged = [lit for lit in labels if lit.language]
        untagged = [lit for lit in labels if not lit.language]
        assert tagged, f"{entry['role']}: no language-tagged rdfs:label"
        assert untagged, f"{entry['role']}: no untagged rdfs:label"
        assert str(tagged[0]) == str(untagged[0])
