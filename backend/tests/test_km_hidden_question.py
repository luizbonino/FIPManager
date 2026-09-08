"""AC4 (spec 04 §6): a hidden question is skipped by CSV/JSON exports and by
the `questionCount` summary, but a FIP may still be patched with an answer
for it (hidden ids stay known question ids -- routers/fips._known_question_ids
is unaffected)."""

from __future__ import annotations


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _sections_with_three_questions() -> list[dict]:
    return [
        {
            "id": "sec1",
            "title": {"en": "Section 1"},
            "questions": [
                {
                    "id": "q1",
                    "text": {"en": "Question 1"},
                    "required": False,
                    "allowMultiple": True,
                },
                {
                    "id": "q2",
                    "text": {"en": "Question 2"},
                    "required": False,
                    "allowMultiple": True,
                },
                {
                    "id": "q3",
                    "text": {"en": "Question 3"},
                    "required": False,
                    "allowMultiple": True,
                },
            ],
        }
    ]


def test_hidden_question_excluded_from_exports_and_counts(client):
    _register(client, "hidden-question@example.com")
    created = client.post(
        "/api/knowledge-models",
        json={
            "id": "hidden-q-test",
            "title": {"en": "Hidden Q Test"},
            "sections": _sections_with_three_questions(),
        },
    )
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag = get1.headers["etag"]
    sections = get1.json()["content"]["sections"]
    sections[0]["questions"][1]["hidden"] = True  # hide q2

    put = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag},
        json={"sections": sections},
    )
    assert put.status_code == 200, put.text

    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text

    fip = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "answers": [
                {"questionId": "q1", "declarations": [{"ferFreeText": "x", "status": "current"}]},
                {"questionId": "q3", "declarations": [{"ferFreeText": "y", "status": "current"}]},
            ],
        },
    )
    assert fip.status_code == 201, fip.text
    fip_id = fip.json()["id"]

    export_json = client.get(f"/api/fips/{fip_id}/export.json").json()
    answer_ids = [a["questionId"] for a in export_json["answers"]]
    assert "q2" not in answer_ids
    assert set(answer_ids) == {"q1", "q3"}

    export_csv = client.get(f"/api/fips/{fip_id}/export.csv")
    csv_text = export_csv.content.decode("utf-8-sig")
    assert ",q2," not in csv_text

    listing = client.get("/api/knowledge-models", params={"mine": True})
    row = next(i for i in listing.json()["items"] if i["id"] == km_id)
    assert row["questionCount"] == 2

    patch_hidden_answer = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "q2",
                    "declarations": [{"ferFreeText": "late", "status": "current"}],
                },
            ]
        },
    )
    assert patch_hidden_answer.status_code == 200, patch_hidden_answer.text
