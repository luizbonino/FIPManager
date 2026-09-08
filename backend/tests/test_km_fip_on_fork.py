"""AC3 (spec 04 §6): a FIP created against a published fork resolves the
edited question text in `export.json`'s `questionnaireRef`/answers, and
`export.csv` still has exactly the 21 columns of spec 01 §3.2 in order."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_fip_on_published_fork_exports_edited_text(client):
    _register(client, "fip-on-fork@example.com")
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag = get1.headers["etag"]
    sections = get1.json()["content"]["sections"]
    sections[0]["questions"][0]["text"]["en"] = "Edited: what identifiers do you use?"

    put = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag},
        json={"sections": sections},
    )
    assert put.status_code == 200, put.text

    published = client.post(
        f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "release"}
    )
    assert published.status_code == 200, published.text

    fip = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": km_id, "version": "1.0.0"}},
    )
    assert fip.status_code == 201, fip.text
    fip_id = fip.json()["id"]

    export_json = client.get(f"/api/fips/{fip_id}/export.json")
    assert export_json.status_code == 200
    doc = export_json.json()
    assert doc["questionnaireRef"] == {
        "id": km_id,
        "version": "1.0.0",
        "title": doc["questionnaireRef"]["title"],
        "source": doc["questionnaireRef"]["source"],
    }
    assert doc["questionnaireRef"]["id"] == km_id
    assert doc["questionnaireRef"]["version"] == "1.0.0"
    first_answer = next(a for a in doc["answers"] if a["questionId"] == "F1-metadata")
    assert first_answer["questionText"] == "Edited: what identifiers do you use?"

    export_csv = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export_csv.status_code == 200
    raw = export_csv.content.decode("utf-8-sig")
    header_row = raw.split("\r\n", 1)[0]
    assert header_row.split(",") == CSV_HEADER
