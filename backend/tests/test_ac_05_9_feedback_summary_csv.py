"""AC9 (spec 05-v1-completion.md §8): GET /api/sessions/{id}/feedback
returns 404 for a non-owner and, for the owner, the exact counts, 2-dp means
and free texts of the posted rows (responses: 0, mean: null when empty);
feedback.csv returns the six columns with a BOM and CRLF."""

from __future__ import annotations

PRIVACY_VERSION = "test-v1"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _make_session(client):
    return client.post(
        "/api/sessions",
        json={
            "title": "ac05-9 session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()


def test_feedback_summary_empty_then_populated(client, client_factory):
    _register(client, "ac05-9-owner@example.com")
    session = _make_session(client)
    session_id = session["id"]

    empty = client.get(f"/api/sessions/{session_id}/feedback")
    assert empty.status_code == 200
    body = empty.json()
    assert body["responses"] == 0
    for q in body["questions"]:
        assert q["mean"] is None
        assert q["counts"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    assert body["comments"] == []

    anon = client_factory()
    for scores, comment in (
        ((4, 5, 3), "Great"),
        ((2, 4, 4), None),
        ((5, 5, 5), "Loved it"),
    ):
        r = anon.post(
            "/api/feedback",
            json={
                "q1": scores[0],
                "q2": scores[1],
                "q3": scores[2],
                "comment": comment,
                "sessionId": session_id,
            },
        )
        assert r.status_code == 201

    filled = client.get(f"/api/sessions/{session_id}/feedback")
    assert filled.status_code == 200
    filled_body = filled.json()
    assert filled_body["responses"] == 3
    q1 = next(q for q in filled_body["questions"] if q["key"] == "q1")
    assert q1["mean"] == round((4 + 2 + 5) / 3, 2)
    assert q1["counts"]["4"] == 1
    assert q1["counts"]["2"] == 1
    assert q1["counts"]["5"] == 1
    comment_texts = {c["text"] for c in filled_body["comments"]}
    assert comment_texts == {"Great", "Loved it"}

    csv_resp = client.get(f"/api/sessions/{session_id}/feedback.csv")
    assert csv_resp.status_code == 200
    raw = csv_resp.content.decode("utf-8-sig")
    lines = [line for line in raw.split("\r\n") if line]
    assert lines[0].split(",") == ["session_id", "created_at", "q1", "q2", "q3", "comment"]
    assert len(lines) == 4  # header + 3 rows
    assert b"\r\n" in csv_resp.content
    assert csv_resp.content.startswith(b"\xef\xbb\xbf")

    stranger = client_factory()
    _register(stranger, "ac05-9-stranger@example.com")
    forbidden = stranger.get(f"/api/sessions/{session_id}/feedback")
    assert forbidden.status_code == 404
