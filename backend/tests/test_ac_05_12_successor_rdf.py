"""AC12 (spec 05-v1-completion.md §8): export.ttl of a planned-replacement
declaration with a successor carries, on the same declaration node, both
fip:declares-planned-replacement-of and fip:declares-planned-use-of, and
types the successor fip:Available-FAIR-Enabling-Resource; a FIP stored
before this change (no successor fields at all) serialises with none of
that -- i.e. the change is purely additive when there's nothing to add,
which is what "byte-identical" comes down to for a graph with no successor
triples in it."""

from __future__ import annotations

from rdflib import RDF, URIRef

from fipm.exporters import fip_url
from fipm.ids import short_id
from fipm.models import Fip
from fipm.rdf import FIP, fip_graph, to_turtle


def _insert_fip(db_session, settings, **overrides):
    defaults = dict(
        owner_id=None,
        session_id=None,
        edit_token_hash=None,
        visibility="public",
        questionnaire_id="test-km",
        questionnaire_version="1.0.0",
        title=None,
        community={"name": "Successor test group"},
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


def test_planned_replacement_with_successor_emits_both_triples_and_types_successor(
    db_session, settings
):
    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [
                {
                    "ferId": "https://example.org/fers/old-registry",
                    "status": "planned-replacement",
                    "successorFerId": "https://example.org/fers/new-registry",
                }
            ],
            "comment": None,
        }
    ]
    fip = _insert_fip(db_session, settings, answers=answers)
    g = fip_graph(db_session, fip, settings)
    fip_iri = URIRef(fip_url(fip, settings))
    decl_iri = URIRef(f"{fip_iri}#decl-F1-metadata-0")

    old = URIRef("https://example.org/fers/old-registry")
    new = URIRef("https://example.org/fers/new-registry")

    assert (decl_iri, FIP["declares-planned-replacement-of"], old) in g
    assert (decl_iri, FIP["declares-planned-use-of"], new) in g
    assert (new, RDF.type, FIP["Available-FAIR-Enabling-Resource"]) in g

    ttl = to_turtle(g)
    assert "declares-planned-use-of" in ttl


def test_planned_replacement_without_successor_emits_no_extra_triple(db_session, settings):
    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [
                {
                    "ferId": "https://example.org/fers/old-registry-2",
                    "status": "planned-replacement",
                }
            ],
            "comment": None,
        }
    ]
    fip = _insert_fip(db_session, settings, answers=answers)
    g = fip_graph(db_session, fip, settings)
    fip_iri = URIRef(fip_url(fip, settings))
    decl_iri = URIRef(f"{fip_iri}#decl-F1-metadata-0")

    assert (decl_iri, FIP["declares-planned-use-of"], None) not in g


def test_repeated_export_of_same_fip_is_byte_identical(db_session, settings):
    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [{"ferFreeText": "In-house tool", "status": "current"}],
            "comment": None,
        }
    ]
    fip = _insert_fip(db_session, settings, answers=answers)
    ttl_1 = to_turtle(fip_graph(db_session, fip, settings))
    ttl_2 = to_turtle(fip_graph(db_session, fip, settings))
    assert ttl_1 == ttl_2
    assert "declares-planned-use-of" not in ttl_1
