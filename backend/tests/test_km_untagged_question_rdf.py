"""AC5 (spec 04 §6): a from-scratch model with one untagged question
(principle=null, ferType=null) answered with a free-text FER and a comment
exports Turtle with no `fip:refers-to-question`/`fip:refers-to-principle`,
a `fipmx:question-id` literal, no fip:-namespace FER-type class on the FER
node, and a comment node typed `fipmx:Answer` -- spec 03-matrix-and-rdf.md
§2.3's already-specified behaviour, pinned here with no code change expected
beyond the hidden-question skip added for spec 04."""

from __future__ import annotations

from fipm.fer_types import get_fer_types


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_untagged_question_rdf_has_no_fip_links(client, settings):
    _register(client, "untagged-rdf@example.com")
    sections = [
        {
            "id": "general",
            "title": {"en": "General"},
            "questions": [
                {
                    "id": "untagged-1",
                    "text": {"en": "An untagged question"},
                    "principle": None,
                    "ferType": None,
                    "required": False,
                    "allowMultiple": True,
                }
            ],
        }
    ]
    created = client.post(
        "/api/knowledge-models",
        json={"id": "untagged-rdf-km", "title": {"en": "Untagged RDF"}, "sections": sections},
    )
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text

    fip = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "untagged-1",
                    "declarations": [{"ferFreeText": "Some free text FER", "status": "current"}],
                    "comment": "a free text comment",
                }
            ],
        },
    )
    assert fip.status_code == 201, fip.text
    fip_id = fip.json()["id"]

    ttl = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert ttl.status_code == 200
    text = ttl.content.decode("utf-8")

    assert "fip:refers-to-question" not in text
    assert "fip:refers-to-principle" not in text
    assert "fipmx:question-id" in text
    assert "untagged-1" in text
    assert "fipmx:Answer" in text

    fer_type_locals = {
        entry["iri"].rsplit("/", 1)[-1] for entry in get_fer_types(settings).values()
    }
    assert fer_type_locals, "expected the FER-type taxonomy fixture to be loaded"
    assert not any(local in text for local in fer_type_locals)
