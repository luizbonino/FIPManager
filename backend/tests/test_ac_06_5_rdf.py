"""AC6 (spec 06-dmp-linkage.md §5): a declaration with evidence gets exactly
one fipmx:dmp-evidence -> the DMP's IRI, that IRI is typed dcso:DMP with
fipmx:dmp-system "FioDMP", fipmx:dmp-section/fipmx:dmp-question-ref
literals are present, and a FIP without evidence emits none of the three."""

from __future__ import annotations

from rdflib import RDF, Graph, Literal, URIRef

from fipm.db import SessionLocal
from fipm.models import Fip
from fipm.rdf import DCSO


def test_declaration_with_evidence_emits_dmp_evidence_and_typed_dmp_node(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac6-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "DMP",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    ).json()
    fip_id = created["id"]

    client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C", "version": "13"}],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "dmpEvidence": {"dmpIndex": 0, "section": "C", "questionRef": "C.3"},
                        }
                    ],
                }
            ],
        },
    )

    resp = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert resp.status_code == 200
    g = Graph().parse(data=resp.text, format="turtle")

    dmp_iri = URIRef("https://fiodmp.fiocruz.br/KQU5N0C")
    fipmx = "https://w3id.org/fipm/ns#"

    evidence_objs = list(g.objects(None, URIRef(fipmx + "dmp-evidence")))
    assert evidence_objs == [dmp_iri]

    assert (dmp_iri, RDF.type, DCSO.DMP) in g
    assert (dmp_iri, URIRef(fipmx + "dmp-system"), Literal("FioDMP")) in g

    decl_subject = next(g.subjects(URIRef(fipmx + "dmp-evidence"), dmp_iri))
    assert (decl_subject, URIRef(fipmx + "dmp-section"), Literal("C")) in g
    assert (decl_subject, URIRef(fipmx + "dmp-question-ref"), Literal("C.3")) in g


def test_fip_without_evidence_emits_none_of_the_three_predicates(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac6-noevidence@example.com",
            "password": "correcthorsebattery",
            "displayName": "DMP",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    ).json()
    fip_id = created["id"]

    resp = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert resp.status_code == 200
    g = Graph().parse(data=resp.text, format="turtle")
    fipmx = "https://w3id.org/fipm/ns#"

    assert (None, URIRef(fipmx + "dmp-evidence"), None) not in g
    assert (None, URIRef(fipmx + "dmp-section"), None) not in g
    assert (None, URIRef(fipmx + "dmp-question-ref"), None) not in g


def test_unresolvable_evidence_still_emits_section_and_question_ref(client):
    """Review finding 4: dmp-section/dmp-question-ref describe where in the
    DMP the evidence lives, which is meaningful even when the DMP itself
    can no longer be resolved to an IRI (here: an out-of-range dmpIndex,
    since relatedDmps was patched down to a single entry after this
    evidence was recorded against index 1) -- they must not be gated on a
    resolved dmpUrl. dmp-evidence/prov:wasDerivedFrom, which *are* an IRI
    reference, correctly stay absent."""
    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac6-unresolvable@example.com",
            "password": "correcthorsebattery",
            "displayName": "DMP",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    ).json()
    fip_id = created["id"]

    with SessionLocal() as db:
        fip = db.get(Fip, fip_id)
        fip.related_dmps = [
            {"url": "https://fiodmp.fiocruz.br/KQU5N0C", "version": None, "system": "FioDMP"}
        ]
        fip.answers = [
            {
                "questionId": "F1-metadata",
                "declarations": [
                    {
                        "ferId": "https://w3id.org/np/doi",
                        "status": "current",
                        "dmpEvidence": {"dmpIndex": 1, "section": "C", "questionRef": "C.3"},
                    }
                ],
                "comment": None,
            }
        ]
        db.commit()

    resp = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert resp.status_code == 200
    g = Graph().parse(data=resp.text, format="turtle")
    fipmx = "https://w3id.org/fipm/ns#"

    assert (None, URIRef(fipmx + "dmp-evidence"), None) not in g

    section_objs = list(g.objects(None, URIRef(fipmx + "dmp-section")))
    assert section_objs == [Literal("C")]
    question_ref_objs = list(g.objects(None, URIRef(fipmx + "dmp-question-ref")))
    assert question_ref_objs == [Literal("C.3")]
