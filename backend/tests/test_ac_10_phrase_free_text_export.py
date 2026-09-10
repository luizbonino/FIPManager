"""spec 10-suggested-phrases-and-other.md: a `question.suggestedPhrases`
entry is authoring metadata only -- when a participant ticks it, the
frontend creates an ordinary declaration with `ferFreeText` equal to the
phrase text (no backend change to FIP answers, exports or RDF). This test
confirms that path already works end to end: a FIP whose declaration's
`ferFreeText` matches a `suggestedPhrases` entry exports fine in JSON, CSV
and Turtle, and round-trips through `POST /api/fips/import`."""

from __future__ import annotations

import csv
import io


def _register(client, email: str) -> None:
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


PHRASE_TEXT = "Apenas texto não estruturado"


def _publish_model_with_phrase_question(client) -> str:
    created = client.post("/api/knowledge-models", json={"title": {"en": "Phrase model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]
    etag = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]
    sections = [
        {
            "id": "sec1",
            "title": {"en": "Section 1"},
            "questions": [
                {
                    "id": "q-with-phrase",
                    "text": {"en": "Question with a suggested phrase"},
                    "ferType": "identifier-service",
                    "suggestedFerIds": ["https://w3id.org/np/doi"],
                    "suggestedPhrases": [{"text": {"en": PHRASE_TEXT, "pt-BR": PHRASE_TEXT}}],
                }
            ],
        }
    ]
    put = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag},
        json={"sections": sections},
    )
    assert put.status_code == 200, put.text
    pub = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert pub.status_code == 200, pub.text
    return km_id


def test_phrase_matching_free_text_declaration_exports_and_roundtrips(client):
    _register(client, "ac10-phrase-export@example.com")
    km_id = _publish_model_with_phrase_question(client)

    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "q-with-phrase",
                    "declarations": [{"ferFreeText": PHRASE_TEXT, "status": "current"}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    # JSON export: the declaration is an ordinary ferFreeText declaration.
    export_json = client.get(f"/api/fips/{fip_id}/export.json")
    assert export_json.status_code == 200
    doc = export_json.json()
    answer = next(a for a in doc["answers"] if a["questionId"] == "q-with-phrase")
    assert answer["declarations"][0]["ferFreeText"] == PHRASE_TEXT
    assert answer["declarations"][0]["status"] == "current"

    # Round trip through import.
    imported = client.post("/api/fips/import", json=doc)
    assert imported.status_code == 201, imported.text
    new_fip = imported.json()
    original = client.get(f"/api/fips/{fip_id}").json()
    assert new_fip["answers"] == original["answers"]

    # CSV export: one row for the question with fer_free_text = the phrase.
    export_csv = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export_csv.status_code == 200
    rows = list(csv.DictReader(io.StringIO(export_csv.text)))
    row = next(r for r in rows if r["question_id"] == "q-with-phrase")
    assert row["fer_free_text"] == PHRASE_TEXT
    assert row["status"] == "current"
    assert row["fer_id"] == ""

    # Turtle export: the declaration carries the free-text FER label.
    export_ttl = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert export_ttl.status_code == 200
    assert PHRASE_TEXT in export_ttl.text
