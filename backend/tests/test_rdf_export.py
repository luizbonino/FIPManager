"""spec 03-matrix-and-rdf.md §2 / §4 items 1-9: `fipm.rdf` and the
`export.ttl` / `export.jsonld` endpoints.

Uses the real gofair-fip-mini-1.0.0 knowledge model (like
test_real_data_smoke.py) and skips cleanly if data/ isn't present.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.compare import isomorphic

from fipm.config import Settings
from fipm.exporters import fip_url
from fipm.ids import short_id
from fipm.importer import ImportSummary, _import_knowledge_models
from fipm.models import Fip, WorkshopSession
from fipm.rdf import (
    FIP,
    KNOWN_QUESTION_INDIVIDUALS,
    TURTLE_HEADER,
    _free_text_hash,
    fip_graph,
    session_graph,
    to_turtle,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"

pytestmark = pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)

KM_ID = "gofair-fip-mini"
KM_VERSION = "1.0.0"


@pytest.fixture()
def real_settings(settings):
    return Settings(
        data_dir=str(REAL_DATA_DIR), db_path=settings.db_path, base_url=settings.base_url
    )


@pytest.fixture()
def real_km_loaded(db_session, real_settings):
    """Import the real knowledge model + FER types into the shared test DB."""
    summary = ImportSummary()
    _import_knowledge_models(db_session, real_settings, summary, force=False)
    return real_settings


def _insert_fip(db_session, settings, **overrides):
    """Insert a Fip row directly, bypassing the API/pydantic layer, so tests
    can freely control the `answers` JSON shape (all five statuses, notes,
    comments, dmpEvidence) without fighting request validation."""
    defaults = dict(
        owner_id=None,
        session_id=None,
        edit_token_hash=None,
        visibility="public",
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        title=None,
        community={"name": "Test group", "description": "desc", "domain": "Public health"},
        related_dmps=[],
        answers=[],
        language="pt-BR",
        license="CC0-1.0",
    )
    defaults.update(overrides)
    fip = Fip(id=short_id(settings.id_prefix), **defaults)
    db_session.add(fip)
    db_session.commit()
    db_session.refresh(fip)
    return fip


FIVE_DECL_ANSWERS = [
    {
        "questionId": "F1-metadata",
        "declarations": [
            {"ferId": "https://www.doi.org/", "status": "current"},
            {"ferId": "https://www.handle.net/", "status": "planned-replacement"},
        ],
        "comment": None,
    },
    {
        "questionId": "F1-data",
        "declarations": [
            {"ferFreeText": "Our own registry", "status": "planned"},
            {"ferFreeText": "n/a", "status": "none"},
        ],
        "comment": None,
    },
    {
        "questionId": "I2-metadata",
        "declarations": [
            {
                "ferFreeText": "Ministério da Saúde vocabulary",
                "status": "planned-development",
                "note": {
                    "en": "No published vocabulary covers this domain.",
                    "pt-BR": "Nenhum vocabulário publicado cobre o domínio.",
                },
            },
        ],
        "comment": "Decidir com a equipa de terminologia.",
    },
]


# --------------------------------------------------------------------------
# AC1 - GET .../export.ttl: 200 text/turtle, parses, FIP subject typed.
# --------------------------------------------------------------------------


def test_ac1_export_ttl_200_parses_and_types_fip(client, real_km_loaded):
    client.post(
        "/api/auth/register",
        json={
            "email": "rdf-ac1@example.com",
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "community": {"name": "AC1 group"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://www.doi.org/", "status": "current"}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    resp = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/turtle")
    assert resp.headers["content-disposition"] == f'attachment; filename="{fip_id}.ttl"'

    g = Graph().parse(data=resp.text, format="turtle")
    subject = URIRef(f"{real_km_loaded.base_url}/fips/{fip_id}")
    assert (subject, RDF.type, FIP["FAIR-Implementation-Profile"]) in g


# --------------------------------------------------------------------------
# AC2 / AC3 - declaration count, one declares-* predicate each, none-status.
# --------------------------------------------------------------------------


def test_ac2_five_declarations_over_three_questions_one_declares_predicate_each(
    db_session, real_km_loaded
):
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)

    decl_subjects = {s for s in g.subjects(RDF.type, FIP["FIP-Declaration"])}
    assert len(decl_subjects) == 5

    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    current_decl = URIRef(f"{fip_iri}#decl-F1-metadata-0")
    replacement_decl = URIRef(f"{fip_iri}#decl-F1-metadata-1")
    planned_decl = URIRef(f"{fip_iri}#decl-F1-data-0")
    dev_decl = URIRef(f"{fip_iri}#decl-I2-metadata-0")

    assert list(g.objects(current_decl, FIP["declares-current-use-of"])) == [
        URIRef("https://www.doi.org/")
    ]
    assert list(g.objects(replacement_decl, FIP["declares-planned-replacement-of"])) == [
        URIRef("https://www.handle.net/")
    ]
    # the planned-replacement declaration must NOT auto-emit declares-planned-use-of.
    assert (replacement_decl, FIP["declares-planned-use-of"], None) not in g

    planned_objs = list(g.objects(planned_decl, FIP["declares-planned-use-of"]))
    assert len(planned_objs) == 1

    dev_objs = list(g.objects(dev_decl, FIP["declares-planned-development-of"]))
    assert len(dev_objs) == 1

    # each of the four declaring declarations carries exactly one declares-* triple.
    declares_predicates = {
        FIP["declares-current-use-of"],
        FIP["declares-planned-use-of"],
        FIP["declares-planned-development-of"],
        FIP["declares-planned-replacement-of"],
    }
    for decl_iri in (current_decl, replacement_decl, planned_decl, dev_decl):
        count = sum(1 for p in declares_predicates if (decl_iri, p, None) in g)
        assert count == 1, f"{decl_iri} has {count} declares-* triples"


def test_ac3_none_declaration_typed_no_choice_and_carries_status(db_session, real_km_loaded):
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    fipmx = real_km_loaded.ext_ns

    none_decl = URIRef(f"{fip_iri}#decl-F1-data-1")
    assert (none_decl, RDF.type, FIP["FIP-Declaration"]) in g
    assert (none_decl, RDF.type, FIP["FIP-No-Choice-Declaration"]) in g
    assert (none_decl, URIRef(fipmx + "declaration-status"), Literal("none")) in g

    declares_predicates = {
        FIP["declares-current-use-of"],
        FIP["declares-planned-use-of"],
        FIP["declares-planned-development-of"],
        FIP["declares-planned-replacement-of"],
    }
    for p in declares_predicates:
        assert (none_decl, p, None) not in g


# --------------------------------------------------------------------------
# AC4 - free-text FER hash IRI, typing, label, dedup across FIPs.
# --------------------------------------------------------------------------


def test_ac4_free_text_fer_hash_iri_typed_and_labelled(db_session, real_km_loaded):
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)

    text = "Ministério da Saúde vocabulary"
    hash_hex = _free_text_hash(text)
    fer_iri = URIRef(f"{real_km_loaded.base_url}/fers/text/{hash_hex}")

    assert (fer_iri, RDF.type, FIP["FAIR-Enabling-Resource"]) in g
    assert (fer_iri, RDF.type, FIP["Structured-vocabulary"]) in g
    assert (fer_iri, RDFS.label, Literal(text, lang="pt-BR")) in g
    fipmx = real_km_loaded.ext_ns
    assert (fer_iri, URIRef(fipmx + "free-text"), Literal(True)) in g


def test_ac4_free_text_fer_dedup_across_fips_in_session_graph(db_session, real_km_loaded):
    answers_a = [
        {
            "questionId": "I2-metadata",
            "declarations": [
                {"ferFreeText": "Ministério da Saúde vocabulary", "status": "planned-development"}
            ],
        }
    ]
    answers_b = [
        {
            "questionId": "I2-metadata",
            "declarations": [
                {"ferFreeText": "  ministério da saúde VOCABULARY  ", "status": "current"}
            ],
        }
    ]
    fip_a = _insert_fip(db_session, real_km_loaded, answers=answers_a)
    fip_b = _insert_fip(db_session, real_km_loaded, answers=answers_b)

    session = WorkshopSession(
        id=short_id(real_km_loaded.id_prefix),
        join_code="ABCDEF",
        owner_id=None,
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        default_language="pt-BR",
        title="dedup session",
        status="open",
    )
    db_session.add(session)
    db_session.commit()

    g = session_graph(db_session, session, [fip_a, fip_b], real_km_loaded)
    fer_nodes = {
        s for s in g.subjects(RDF.type, FIP["FAIR-Enabling-Resource"]) if "/fers/text/" in str(s)
    }
    assert len(fer_nodes) == 1


# --------------------------------------------------------------------------
# AC5 - considerations per note-langmap key, one answer-comment, unanswered
# questions contribute nothing.
# --------------------------------------------------------------------------


def test_ac5_considerations_per_lang_and_single_answer_comment_and_no_unanswered_triples(
    db_session, real_km_loaded
):
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))

    dev_decl = URIRef(f"{fip_iri}#decl-I2-metadata-0")
    considerations = set(g.objects(dev_decl, FIP.considerations))
    assert considerations == {
        Literal("No published vocabulary covers this domain.", lang="en"),
        Literal("Nenhum vocabulário publicado cobre o domínio.", lang="pt-BR"),
    }

    fipmx = real_km_loaded.ext_ns
    answer_iri = URIRef(f"{fip_iri}#answer-I2-metadata")
    comments = list(g.objects(answer_iri, URIRef(fipmx + "answer-comment")))
    assert comments == [Literal("Decidir com a equipa de terminologia.", lang="pt-BR")]

    # a question the FIP never answered (e.g. F2) contributes nothing.
    assert not any("F2" in str(s) for s in g.subjects() if str(s).startswith(str(fip_iri) + "#"))


# --------------------------------------------------------------------------
# AC6 - session export union graph.
# --------------------------------------------------------------------------


def test_ac6_session_export_union_of_fip_graphs_plus_session_node(db_session, real_km_loaded):
    fips = [
        _insert_fip(
            db_session,
            real_km_loaded,
            answers=[
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://www.doi.org/", "status": "current"}],
                }
            ],
        )
        for _ in range(3)
    ]
    session = WorkshopSession(
        id=short_id(real_km_loaded.id_prefix),
        join_code="GHIJKL",
        owner_id=None,
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        default_language="pt-BR",
        title="union session",
        status="open",
    )
    db_session.add(session)
    db_session.commit()

    individual_graphs = [fip_graph(db_session, f, real_km_loaded) for f in fips]
    union_triples = set()
    for ig in individual_graphs:
        union_triples |= set(ig)

    sg = session_graph(db_session, session, fips, real_km_loaded)

    session_iri = URIRef(f"{real_km_loaded.base_url}/sessions/{session.id}")
    fipmx = real_km_loaded.ext_ns
    assert (session_iri, RDF.type, URIRef(fipmx + "Workshop-Session")) in sg
    has_fip_objs = set(sg.objects(session_iri, URIRef(fipmx + "has-fip")))
    assert has_fip_objs == {URIRef(fip_url(f, real_km_loaded)) for f in fips}
    assert len(has_fip_objs) == 3

    for f in fips:
        assert (
            URIRef(fip_url(f, real_km_loaded)),
            RDF.type,
            FIP["FAIR-Implementation-Profile"],
        ) in sg

    session_only_triples = {t for t in sg if t[0] == session_iri}
    fip_content_triples = set(sg) - session_only_triples
    assert fip_content_triples == union_triples


# --------------------------------------------------------------------------
# AC7 - auth: session export (owner/admin/other/anon), private FIP export.
# --------------------------------------------------------------------------


def test_ac7_session_export_ttl_auth(client_factory, real_km_loaded):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "rdf-ac7-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "O",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ac7",
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "defaultLanguage": "pt-BR",
        },
    ).json()
    for i in range(3):
        owner.post(
            "/api/fips",
            json={
                "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
                "sessionId": session["id"],
                "joinCode": session["joinCode"],
                "community": {"name": f"g{i}"},
                "answers": [],
            },
        )

    ok = owner.get(f"/api/sessions/{session['id']}/export.ttl")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/turtle")

    other = client_factory()
    other.post(
        "/api/auth/register",
        json={
            "email": "rdf-ac7-other@example.com",
            "password": "correcthorsebattery",
            "displayName": "N",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert other.get(f"/api/sessions/{session['id']}/export.ttl").status_code == 404

    anon = client_factory()
    assert anon.get(f"/api/sessions/{session['id']}/export.ttl").status_code == 401

    admin = client_factory()
    reg = admin.post(
        "/api/auth/register",
        json={
            "email": "rdf-ac7-admin@example.com",
            "password": "correcthorsebattery",
            "displayName": "A",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    admin_id = reg.json()["id"]
    from fipm.models import User

    with __import__("fipm.db", fromlist=["SessionLocal"]).SessionLocal() as db:
        db.query(User).filter(User.id == admin_id).update({"role": "admin"})
        db.commit()

    assert admin.get(f"/api/sessions/{session['id']}/export.ttl").status_code == 200


def test_ac7_private_fip_export_ttl_owner_edit_token_and_non_owner(client_factory, real_km_loaded):
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "rdf-ac7-fac@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "ac7-private",
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "defaultLanguage": "pt-BR",
        },
    ).json()

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "visibility": "private",
            "community": {"name": "private group"},
            "answers": [],
        },
    ).json()
    fip_id, token = created["id"], created["editToken"]

    anon = client_factory()
    assert anon.get(f"/api/fips/{fip_id}/export.ttl").status_code == 404
    ok_token = anon.get(f"/api/fips/{fip_id}/export.ttl", headers={"X-Edit-Token": token})
    assert ok_token.status_code == 200

    # the session owner (facilitator) may also read it.
    assert facilitator.get(f"/api/fips/{fip_id}/export.ttl").status_code == 200


# --------------------------------------------------------------------------
# AC8 - export.jsonld: 200, valid @context, same triple count + isomorphic.
# --------------------------------------------------------------------------


def test_ac8_jsonld_same_triple_count_and_isomorphic_to_turtle(client, real_km_loaded):
    client.post(
        "/api/auth/register",
        json={
            "email": "rdf-ac8@example.com",
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "community": {"name": "AC8 group"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {"ferId": "https://www.doi.org/", "status": "current"},
                        {"ferFreeText": "Custom vocab", "status": "planned"},
                    ],
                    "comment": "a comment",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    ttl_resp = client.get(f"/api/fips/{fip_id}/export.ttl")
    jsonld_resp = client.get(f"/api/fips/{fip_id}/export.jsonld")
    assert jsonld_resp.status_code == 200
    assert jsonld_resp.headers["content-type"].startswith("application/ld+json")
    assert jsonld_resp.headers["content-disposition"] == f'attachment; filename="{fip_id}.jsonld"'

    doc = jsonld_resp.json()
    assert "@context" in doc

    g_ttl = Graph().parse(data=ttl_resp.text, format="turtle")
    g_jsonld = Graph().parse(data=jsonld_resp.text, format="json-ld")

    assert len(g_ttl) == len(g_jsonld)
    assert isomorphic(g_ttl, g_jsonld)


# --------------------------------------------------------------------------
# AC9 - every minted IRI starts with settings.base_url; changing it changes
# every minted IRI and nothing else.
# --------------------------------------------------------------------------


def test_ac9_base_url_change_mints_new_iris_only(db_session, real_km_loaded):
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)

    settings_a = real_km_loaded
    settings_b = Settings(
        data_dir=settings_a.data_dir, db_path=settings_a.db_path, base_url="https://other.example"
    )

    g_a = fip_graph(db_session, fip, settings_a)
    g_b = fip_graph(db_session, fip, settings_b)

    assert len(g_a) == len(g_b)

    # Every subject/object IRI FIP Manager mints starts with settings_a.base_url;
    # substituting it for settings_b.base_url reproduces g_b triple-for-triple
    # (external FER/ORCID IRIs and literal content, which never contain the
    # base URL, are untouched by the substitution and so match either way).
    def _shift(term):
        if isinstance(term, URIRef) and str(term).startswith(settings_a.base_url):
            return URIRef(str(term).replace(settings_a.base_url, settings_b.base_url, 1))
        return term

    shifted = {(_shift(s), _shift(p), _shift(o)) for s, p, o in g_a}
    assert shifted == set(g_b)

    # every FIP-Manager-minted subject in g_b does start with the new base_url.
    fip_iri_b = URIRef(fip_url(fip, settings_b))
    assert (fip_iri_b, RDF.type, FIP["FAIR-Implementation-Profile"]) in g_b
    for s in g_b.subjects(RDF.type, FIP["FIP-Declaration"]):
        assert str(s).startswith(settings_b.base_url)

    # audit finding 2: the fipmx VOCABULARY namespace is fixed, independent
    # of base_url -- every fipmx predicate/type used is identical between
    # the two graphs, not merely reproduced by the base_url substitution
    # above (unlike instance IRIs, it never contains settings_a.base_url).
    assert settings_a.ext_ns == settings_b.ext_ns
    fipmx_terms_a = {p for p in g_a.predicates() if str(p).startswith(settings_a.ext_ns)}
    fipmx_terms_a |= {
        o for o in g_a.objects(None, RDF.type) if str(o).startswith(settings_a.ext_ns)
    }
    assert fipmx_terms_a  # sanity: the fixture actually exercises fipmx terms
    fipmx_terms_b = {p for p in g_b.predicates() if str(p).startswith(settings_b.ext_ns)}
    fipmx_terms_b |= {
        o for o in g_b.objects(None, RDF.type) if str(o).startswith(settings_b.ext_ns)
    }
    assert fipmx_terms_a == fipmx_terms_b


def test_ac9_ext_ns_fixed_by_default_and_overridable_via_setting(db_session, real_km_loaded):
    """audit finding 2: fipmx defaults to the fixed `https://w3id.org/fipm/ns#`
    regardless of base_url, and is overridable independently via
    FIPM_EXT_NS (here passed directly as the `ext_ns` setting)."""
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)

    settings_default = real_km_loaded
    g_default = fip_graph(db_session, fip, settings_default)
    assert settings_default.ext_ns == "https://w3id.org/fipm/ns#"
    assert any(str(p).startswith("https://w3id.org/fipm/ns#") for p in g_default.predicates())

    settings_custom_ns = Settings(
        data_dir=settings_default.data_dir,
        db_path=settings_default.db_path,
        base_url=settings_default.base_url,
        ext_ns="https://example.org/custom-fipmx#",
    )
    g_custom = fip_graph(db_session, fip, settings_custom_ns)
    assert any(
        str(p).startswith("https://example.org/custom-fipmx#") for p in g_custom.predicates()
    )
    assert not any(str(p).startswith("https://w3id.org/fipm/ns#") for p in g_custom.predicates())


# --------------------------------------------------------------------------
# FAIR-ontology audit findings 1, 3-8, 12.
# --------------------------------------------------------------------------


def test_audit1_answer_comment_uses_fipmx_refers_to_question_not_fip(db_session, real_km_loaded):
    """finding 1: fip:refers-to-question has rdfs:domain fip:FIP-Declaration;
    using it on a fipmx:Answer node would mistype it as a declaration."""
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    fipmx = real_km_loaded.ext_ns

    answer_iri = URIRef(f"{fip_iri}#answer-I2-metadata")
    assert (answer_iri, FIP["refers-to-question"], None) not in g
    assert (
        answer_iri,
        URIRef(fipmx + "refers-to-question"),
        FIP["FIP-Question-I2-MD"],
    ) in g
    # declarations still use the ontology's own property (its domain matches).
    dev_decl = URIRef(f"{fip_iri}#decl-I2-metadata-0")
    assert (dev_decl, FIP["refers-to-question"], FIP["FIP-Question-I2-MD"]) in g


def test_audit3_declared_by_moved_off_fip_node_kept_on_declarations(db_session, real_km_loaded):
    """finding 3: fip:declared-by has domain fip:FAIR-Declaration, not the
    FIP; the FIP node uses fipmx:declared-by-community instead, while each
    declaration (a FAIR-Declaration subclass) keeps fip:declared-by."""
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    fipmx = real_km_loaded.ext_ns
    community_iri = URIRef(f"{fip_iri}#community")

    assert (fip_iri, FIP["declared-by"], None) not in g
    assert (fip_iri, URIRef(fipmx + "declared-by-community"), community_iri) in g

    decl_iri = URIRef(f"{fip_iri}#decl-F1-metadata-0")
    assert (decl_iri, FIP["declared-by"], community_iri) in g


def test_audit4_research_domain_iri_vs_dcterms_subject_fallback(db_session, real_km_loaded):
    """finding 4: fip:has-research-domain is an ObjectProperty -- a plain
    text domain becomes dcterms:subject, only an http(s) IRI value uses
    fip:has-research-domain directly."""
    from fipm.rdf import DCTERMS

    fip_text = _insert_fip(
        db_session,
        real_km_loaded,
        community={"name": "g", "domain": "Public health"},
    )
    g_text = fip_graph(db_session, fip_text, real_km_loaded)
    community_iri = URIRef(f"{fip_url(fip_text, real_km_loaded)}#community")
    assert (community_iri, FIP["has-research-domain"], None) not in g_text
    assert (community_iri, DCTERMS.subject, Literal("Public health", lang="pt-BR")) in g_text

    fip_iri_domain = _insert_fip(
        db_session,
        real_km_loaded,
        community={"name": "g", "domain": "https://example.org/domains/public-health"},
    )
    g_iri = fip_graph(db_session, fip_iri_domain, real_km_loaded)
    community_iri2 = URIRef(f"{fip_url(fip_iri_domain, real_km_loaded)}#community")
    assert (
        community_iri2,
        FIP["has-research-domain"],
        URIRef("https://example.org/domains/public-health"),
    ) in g_iri
    assert (community_iri2, DCTERMS.subject, None) not in g_iri


def test_audit5_data_steward_without_orcid_mints_foaf_person(db_session, real_km_loaded):
    """finding 5: without a verified ORCID, has-data-steward must point to a
    minted foaf:Person node, not a bare name literal."""
    from rdflib.namespace import FOAF

    fip = _insert_fip(
        db_session,
        real_km_loaded,
        community={"name": "g", "dataSteward": {"name": "Jacintha Schultes"}},
    )
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    community_iri = URIRef(f"{fip_iri}#community")
    steward_iri = URIRef(f"{fip_iri}#data-steward")

    assert (community_iri, FIP["has-data-steward"], Literal("Jacintha Schultes")) not in g
    assert (community_iri, FIP["has-data-steward"], steward_iri) in g
    assert (steward_iri, RDF.type, FOAF.Person) in g
    assert (steward_iri, RDFS.label, Literal("Jacintha Schultes")) in g
    assert (steward_iri, FOAF.name, Literal("Jacintha Schultes")) in g


def test_audit6_none_status_keeps_fer_text_as_consideration(db_session, real_km_loaded):
    """finding 6: a "none"-status declaration must not silently drop its FER
    label/free text; it survives as a fip:considerations literal."""
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    none_decl = URIRef(f"{fip_iri}#decl-F1-data-1")

    assert (none_decl, FIP.considerations, Literal("n/a", lang="pt-BR")) in g
    # and no FER node is minted for a "none" declaration.
    declares_predicates = {
        FIP["declares-current-use-of"],
        FIP["declares-planned-use-of"],
        FIP["declares-planned-development-of"],
        FIP["declares-planned-replacement-of"],
    }
    for p in declares_predicates:
        assert (none_decl, p, None) not in g


def test_audit7_fer_typed_available_or_to_be_developed_by_status(db_session, real_km_loaded):
    """finding 7: a FER is additionally typed fip:Available-FAIR-Enabling-
    Resource for current/planned/planned-replacement, or fip:FAIR-Enabling-
    Resource-to-be-Developed for planned-development."""
    fip = _insert_fip(db_session, real_km_loaded, answers=FIVE_DECL_ANSWERS)
    g = fip_graph(db_session, fip, real_km_loaded)

    doi_fer = URIRef("https://www.doi.org/")  # status = current
    assert (doi_fer, RDF.type, FIP["Available-FAIR-Enabling-Resource"]) in g
    assert (doi_fer, RDF.type, FIP["FAIR-Enabling-Resource-to-be-Developed"]) not in g

    handle_fer = URIRef("https://www.handle.net/")  # status = planned-replacement
    assert (handle_fer, RDF.type, FIP["Available-FAIR-Enabling-Resource"]) in g

    dev_text_fer = URIRef(
        f"{real_km_loaded.base_url}/fers/text/{_free_text_hash('Ministério da Saúde vocabulary')}"
    )  # status = planned-development
    assert (dev_text_fer, RDF.type, FIP["FAIR-Enabling-Resource-to-be-Developed"]) in g
    assert (dev_text_fer, RDF.type, FIP["Available-FAIR-Enabling-Resource"]) not in g


def test_audit8_km_source_dict_with_url_becomes_uriref_plus_citation(db_session, real_km_loaded):
    """finding 8: a dict source with a "url" becomes dcterms:source <url>
    plus dcterms:bibliographicCitation "name"@en.

    The importer flattens the source to its name in the `source` column, so
    `fip_graph` reads the full {"name", "url"} object from the stored
    knowledge-model document (`content["source"]`)."""
    from fipm.models import KnowledgeModel
    from fipm.rdf import DCTERMS

    fip = _insert_fip(db_session, real_km_loaded, answers=[])
    km_row = db_session.get(KnowledgeModel, (KM_ID, KM_VERSION))
    expected = km_row.content["source"]
    assert isinstance(expected, dict) and expected.get("url")

    g = fip_graph(db_session, fip, real_km_loaded)
    km_iri = URIRef(f"{real_km_loaded.base_url}/knowledge-models/{KM_ID}/{KM_VERSION}")

    sources = list(g.objects(km_iri, DCTERMS.source))
    assert sources == [URIRef(expected["url"])]
    citations = list(g.objects(km_iri, DCTERMS.bibliographicCitation))
    assert citations == [Literal(expected["name"], lang="en")]


def test_audit12_session_title_language_tagged(db_session, real_km_loaded):
    fip = _insert_fip(db_session, real_km_loaded, answers=[])
    session = WorkshopSession(
        id=short_id(real_km_loaded.id_prefix),
        join_code="MNOPQR",
        owner_id=None,
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        default_language="pt-BR",
        title="sessão de teste",
        status="open",
    )
    db_session.add(session)
    db_session.commit()

    g = session_graph(db_session, session, [fip], real_km_loaded)
    session_iri = URIRef(f"{real_km_loaded.base_url}/sessions/{session.id}")
    from fipm.rdf import DCTERMS

    assert (session_iri, DCTERMS.title, Literal("sessão de teste", lang="pt-BR")) in g


def test_audit12_dmp_typed_dcso_dmp_not_fipmx(db_session, real_km_loaded):
    """finding 12: dcso:DMP (RDA DMP Common Standard ontology) replaces the
    home-grown fipmx:Data-Management-Plan class."""
    from fipm.rdf import DCSO

    fip = _insert_fip(
        db_session,
        real_km_loaded,
        answers=[],
        related_dmps=[{"url": "https://fiodmp.fiocruz.br/KQU5N0C", "version": "13"}],
    )
    g = fip_graph(db_session, fip, real_km_loaded)
    dmp_iri = URIRef("https://fiodmp.fiocruz.br/KQU5N0C")
    fipmx = real_km_loaded.ext_ns

    assert (dmp_iri, RDF.type, DCSO.DMP) in g
    assert (dmp_iri, RDF.type, URIRef(fipmx + "Data-Management-Plan")) not in g


def test_audit12_known_principle_ids_whitelist_has_15_entries(db_session, real_km_loaded):
    from fipm.rdf import FAIR, KNOWN_PRINCIPLE_IDS

    assert KNOWN_PRINCIPLE_IDS == {
        "F1",
        "F2",
        "F3",
        "F4",
        "A1",
        "A1.1",
        "A1.2",
        "A2",
        "I1",
        "I2",
        "I3",
        "R1",
        "R1.1",
        "R1.2",
        "R1.3",
    }

    # a principle outside the whitelist is skipped rather than minted.
    fip = _insert_fip(
        db_session,
        real_km_loaded,
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"ferId": "https://www.doi.org/", "status": "current"}],
            }
        ],
    )
    g = fip_graph(db_session, fip, real_km_loaded)
    assert (None, FIP["refers-to-principle"], FAIR["R2"]) not in g
    assert (None, FIP["refers-to-principle"], FAIR["F1"]) in g


def test_audit12_ontology_credit_present_as_rdfs_comment_triple(db_session, real_km_loaded):
    """finding 12: the CC0 ontology-credit must also be a triple (so it
    survives into JSON-LD), not only the Turtle comment header."""
    from fipm.rdf import ONTOLOGY_CREDIT_TEXT

    fip = _insert_fip(db_session, real_km_loaded, answers=[])
    g = fip_graph(db_session, fip, real_km_loaded)
    fip_iri = URIRef(fip_url(fip, real_km_loaded))
    assert (fip_iri, RDFS.comment, Literal(ONTOLOGY_CREDIT_TEXT, lang="en")) in g


def test_audit12_km_rights_language_tagged_en(db_session, real_km_loaded):
    from fipm.rdf import DCTERMS

    fip = _insert_fip(db_session, real_km_loaded, answers=[])
    g = fip_graph(db_session, fip, real_km_loaded)
    km_iri = URIRef(f"{real_km_loaded.base_url}/knowledge-models/{KM_ID}/{KM_VERSION}")
    rights = list(g.objects(km_iri, DCTERMS.rights))
    assert len(rights) == 1
    assert rights[0].language == "en"


# --------------------------------------------------------------------------
# spec 03 §2.7 - the worked Turtle example parses, and our own output for
# equivalent input has the same number of declarations.
# --------------------------------------------------------------------------

SPEC_EXAMPLE_TTL = """
# FIP exported by FIP Manager. Ontology terms: FIP Ontology (https://w3id.org/fair/fip/terms/), CC0 1.0.
# Questionnaire content: FIP mini-questionnaire v2.0.0, CC BY-SA 4.0, GO FAIR Foundation. `this:` = the FIP's own fragment namespace.
@prefix fip: <https://w3id.org/fair/fip/terms/> .   @prefix fair: <https://w3id.org/fair/principles/terms/> .
@prefix dcterms: <http://purl.org/dc/terms/> .      @prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .  @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix fipmx: <https://fipm.example.org/ns#> .     @prefix this: <https://fipm.example.org/fips/7Q2M8XKD#> .
<https://fipm.example.org/fips/7Q2M8XKD> a fip:FAIR-Implementation-Profile ;
    dcterms:title "CONFOA 2026 grupo A"@pt-BR ; dcterms:language "pt-BR" ; dcterms:license <https://creativecommons.org/publicdomain/zero/1.0/> ;
    dcterms:created "2026-10-06T09:12:03Z"^^xsd:dateTime ; dcterms:modified "2026-10-06T09:41:55Z"^^xsd:dateTime ;
    dcterms:conformsTo <https://fipm.example.org/knowledge-models/gofair-fip-mini/1.0.0> ; fip:declared-by this:community ;
    fipmx:has-declaration this:decl-F1-data-0 , this:decl-I2-metadata-0 ;
    prov:wasDerivedFrom <https://fiodmp.fiocruz.br/KQU5N0C> .
<https://fiodmp.fiocruz.br/KQU5N0C> a fipmx:Data-Management-Plan ; fipmx:dmp-version "13" ; fipmx:dmp-system "FioDMP" .
this:community a fip:FAIR-Implementation-Community ; dcterms:title "CONFOA 2026 grupo A"@pt-BR ;
    dcterms:description "Saúde pública, dados de vigilância."@pt-BR ; fip:has-research-domain "Saúde pública"@pt-BR ;
    fip:has-data-steward <https://orcid.org/0000-0002-1825-0097> .
<https://fipm.example.org/knowledge-models/gofair-fip-mini/1.0.0> dcterms:title "FIP mini-questionnaire"@en ; dcterms:hasVersion "1.0.0" ;
    dcterms:source "GO FAIR FIP mini-questionnaire" ; dcterms:license <https://creativecommons.org/licenses/by-sa/4.0/> ;
    dcterms:rights "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0." ;
    dcterms:creator <https://orcid.org/0000-0001-8888-635X> , <https://orcid.org/0000-0003-2195-3997> , "Jacintha Schultes" .
# status = current, catalogue FER
this:decl-F1-data-0 a fip:FIP-Declaration ; fip:declared-by this:community ; fipmx:declaration-index 0 ;
    fip:refers-to-question fip:FIP-Question-F1-D ; fip:refers-to-principle fair:F1 ;
    fip:declares-current-use-of <https://www.doi.org/> ; fipmx:declaration-status "current" .
<https://www.doi.org/> a fip:FAIR-Enabling-Resource , fip:Identifier-service ; rdfs:label "DOI"@en .
# status = planned-development, free-text FER, with a consideration and a question comment
this:decl-I2-metadata-0 a fip:FIP-Declaration ; fip:declared-by this:community ; fipmx:declaration-index 0 ;
    fip:refers-to-question fip:FIP-Question-I2-MD ; fip:refers-to-principle fair:I2 ; fipmx:declaration-status "planned-development" ;
    fip:declares-planned-development-of <https://fipm.example.org/fers/text/55c036a2b284564b> ;
    fip:considerations "Nenhum vocabulário publicado cobre o domínio."@pt-BR .
<https://fipm.example.org/fers/text/55c036a2b284564b> a fip:FAIR-Enabling-Resource , fip:Structured-vocabulary ;
    rdfs:label "Ministério da Saúde vocabulary"@pt-BR ; fipmx:free-text true .
this:answer-I2-metadata a fipmx:Answer ; fip:refers-to-question fip:FIP-Question-I2-MD ;
    fipmx:question-id "I2-metadata" ; fipmx:answer-comment "Decidir com a equipa de terminologia."@pt-BR .
"""


def test_spec_2_7_example_parses_and_matches_our_declaration_count(db_session, real_km_loaded):
    example_g = Graph().parse(data=SPEC_EXAMPLE_TTL, format="turtle")
    example_decl_count = len(set(example_g.subjects(RDF.type, FIP["FIP-Declaration"])))
    assert example_decl_count == 2

    # build the equivalent FIP through fip_graph and check it declares the
    # same number of fip:FIP-Declaration subjects.
    settings_ex = Settings(
        data_dir=real_km_loaded.data_dir,
        db_path=real_km_loaded.db_path,
        base_url="https://fipm.example.org",
    )
    fip = _insert_fip(
        db_session,
        settings_ex,
        language="pt-BR",
        license="CC0-1.0",
        community={
            "name": "CONFOA 2026 grupo A",
            "description": "Saúde pública, dados de vigilância.",
            "domain": "Saúde pública",
        },
        answers=[
            {
                "questionId": "F1-data",
                "declarations": [{"ferId": "https://www.doi.org/", "status": "current"}],
            },
            {
                "questionId": "I2-metadata",
                "declarations": [
                    {
                        "ferFreeText": "Ministério da Saúde vocabulary",
                        "status": "planned-development",
                        "note": {"pt-BR": "Nenhum vocabulário publicado cobre o domínio."},
                    }
                ],
                "comment": "Decidir com a equipa de terminologia.",
            },
        ],
    )
    g = fip_graph(db_session, fip, settings_ex)
    our_decl_count = len(set(g.subjects(RDF.type, FIP["FIP-Declaration"])))
    assert our_decl_count == example_decl_count == 2


def test_known_question_individuals_count_is_21():
    assert len(KNOWN_QUESTION_INDIVIDUALS) == 21


def test_to_turtle_includes_ontology_credit_header(db_session, real_km_loaded):
    fip = _insert_fip(db_session, real_km_loaded, answers=[])
    g = fip_graph(db_session, fip, real_km_loaded)
    text = to_turtle(g)
    assert text.startswith(TURTLE_HEADER)
