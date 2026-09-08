"""AC10: GET /fips/{id}/export.json follows the §3.1 shape with language
fallback (pt-PT -> pt-BR -> en), and POST /fips/import round-trips it into an
equal FIP (answers, community, relatedDMPs, language, license, questionnaireRef)."""

from __future__ import annotations


def test_export_json_language_fallback_and_import_roundtrip(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "ac10-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "AC10",
        },
    )

    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [
                {
                    "ferId": "https://w3id.org/np/doi",
                    "status": "current",
                    "note": {"pt-PT": "nota em pt-PT"},
                }
            ],
            "comment": "c1",
        },
        {
            "questionId": "F2",
            "declarations": [
                {
                    "ferFreeText": "In-house schema",
                    "status": "planned",
                    "note": {"pt-PT": "outra nota"},
                }
            ],
            "comment": None,
        },
    ]
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "language": "pt-PT",
            "answers": answers,
            "community": {"name": "Test Community"},
        },
    )
    assert created.status_code == 201
    fip_id = created.json()["id"]

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    assert export.headers["content-disposition"].startswith("attachment")
    doc = export.json()

    assert doc["exportVersion"] == 1
    # KM title has no pt-PT -> falls back to pt-BR.
    assert doc["questionnaireRef"]["title"] == "Modelo de conhecimento de teste"

    f1_answer = next(a for a in doc["answers"] if a["questionId"] == "F1-metadata")
    # F1 question text has no pt-PT -> falls back to pt-BR.
    assert f1_answer["questionText"] == "Quais identificadores você usa?"
    assert f1_answer["declarations"][0]["note"] == "nota em pt-PT"
    assert f1_answer["declarations"][0]["fer"]["id"] == "https://w3id.org/np/doi"
    assert f1_answer["declarations"][0]["fer"]["label"] == "DOI"

    imported = client.post("/api/fips/import", json=doc)
    assert imported.status_code == 201
    new_fip = imported.json()
    assert new_fip["id"] != fip_id

    original = client.get(f"/api/fips/{fip_id}").json()
    assert new_fip["answers"] == original["answers"]
    assert new_fip["community"] == original["community"]
    assert new_fip["relatedDmps"] == original["relatedDmps"]
    assert new_fip["language"] == original["language"]
    assert new_fip["license"] == original["license"]
    assert new_fip["questionnaireId"] == original["questionnaireId"]
    assert new_fip["questionnaireVersion"] == original["questionnaireVersion"]
