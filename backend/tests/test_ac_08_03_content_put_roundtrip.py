"""spec 08-workshop-picklists.md §6 AC3: `PUT .../content` with a valid
picklist model returns 200 and a new ETag; the round trip through
`GET .../export.json` preserves all five new fields byte-for-byte."""

from __future__ import annotations


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


def test_content_put_with_picklist_fields_roundtrips_through_export(client):
    _register(client, "ac08-03@example.com")
    created = client.post("/api/knowledge-models", json={"title": {"en": "Picklist model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert get1.status_code == 200
    etag1 = get1.headers["etag"]

    sections = [
        {
            "id": "sec1",
            "title": {"en": "Section 1"},
            "questions": [
                {
                    "id": "q1",
                    "text": {"en": "Question 1"},
                    "ferType": "identifier-service",
                    "suggestedFerIds": ["https://w3id.org/np/doi"],
                    "allowFreeText": True,
                }
            ],
        }
    ]
    inline_fers = [
        {
            "id": "https://fipm.example.org/fers/draft/55c036a2b284564b",
            "label": {"pt-BR": "Vocabulário do Ministério da Saúde"},
            "type": "structured-vocabulary",
            "homepage": None,
        }
    ]
    body = {
        "sections": sections,
        "inlineFers": inline_fers,
        "defaultDeclarationStatus": "current",
        "compactDeclarations": True,
    }
    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content", headers={"If-Match": etag1}, json=body
    )
    assert put1.status_code == 200, put1.text
    etag2 = put1.headers["etag"]
    assert etag2 != etag1

    exported = client.get(f"/api/knowledge-models/{km_id}/1.0.0/export.json")
    assert exported.status_code == 200
    doc = exported.json()
    assert doc["sections"] == sections
    assert doc["inlineFers"] == inline_fers
    assert doc["defaultDeclarationStatus"] == "current"
    assert doc["compactDeclarations"] is True

    # A second GET (of the row directly, not the export document) sees the
    # same fields inside `content`, confirming the PUT actually persisted
    # them, not just echoed them back in the response.
    get2 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert get2.status_code == 200
    content2 = get2.json()["content"]
    assert content2["inlineFers"] == inline_fers
    assert content2["defaultDeclarationStatus"] == "current"
    assert content2["compactDeclarations"] is True
    assert content2["sections"][0]["questions"][0]["suggestedFerIds"] == ["https://w3id.org/np/doi"]
    assert content2["sections"][0]["questions"][0]["allowFreeText"] is True
