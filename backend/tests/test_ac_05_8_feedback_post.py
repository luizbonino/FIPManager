"""AC8 (spec 05-v1-completion.md §8): POST /api/feedback with scores in 1-5
returns 201 and stores no user id or IP; 0 or 6 -> 422; a 6th post from one
IP inside an hour -> 429 with Retry-After; an unknown sessionId -> 404; with
FIPM_FEEDBACK_ENABLED=false -> 403 feedback_disabled."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import Feedback


def test_feedback_post_recorded_anonymously(client):
    r = client.post("/api/feedback", json={"q1": 4, "q2": 5, "q3": 3, "comment": "Nice tool"})
    assert r.status_code == 201
    assert r.json() == {"status": "recorded"}

    with SessionLocal() as db:
        row = db.query(Feedback).filter(Feedback.comment == "Nice tool").one()
        assert row.session_id is None
        assert row.fip_id is None
        assert not hasattr(row, "user_id")
        assert not hasattr(row, "ip")


def test_feedback_post_out_of_range_scores_422(client):
    too_low = client.post("/api/feedback", json={"q1": 0, "q2": 3, "q3": 3})
    assert too_low.status_code == 422

    too_high = client.post("/api/feedback", json={"q1": 3, "q2": 6, "q3": 3})
    assert too_high.status_code == 422


def test_feedback_post_unknown_session_and_fip_404(client):
    bad_session = client.post(
        "/api/feedback", json={"q1": 3, "q2": 3, "q3": 3, "sessionId": "doesnotexist"}
    )
    assert bad_session.status_code == 404

    bad_fip = client.post(
        "/api/feedback", json={"q1": 3, "q2": 3, "q3": 3, "fipId": "doesnotexist"}
    )
    assert bad_fip.status_code == 404


def test_feedback_post_rate_limited_after_five_per_hour(client):
    for _ in range(5):
        r = client.post("/api/feedback", json={"q1": 3, "q2": 3, "q3": 3})
        assert r.status_code == 201

    sixth = client.post("/api/feedback", json={"q1": 3, "q2": 3, "q3": 3})
    assert sixth.status_code == 429
    assert "Retry-After" in sixth.headers


def test_feedback_post_disabled_returns_403(client, monkeypatch):
    from fipm.config import get_settings

    monkeypatch.setenv("FIPM_FEEDBACK_ENABLED", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/api/feedback", json={"q1": 3, "q2": 3, "q3": 3})
        assert r.status_code == 403
        assert r.json()["detail"] == "feedback_disabled"
    finally:
        get_settings.cache_clear()
