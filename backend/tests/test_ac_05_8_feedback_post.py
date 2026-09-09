"""AC8 (spec 05-v1-completion.md §8): POST /api/feedback with scores in 1-5
returns 201 and stores no user id or IP; 0 or 6 -> 422; with
FIPM_FEEDBACK_ENABLED=false -> 403 feedback_disabled.

Review finding 7: an unknown *or unreadable* sessionId/fipId used to return
404, making this public, unauthenticated endpoint an existence oracle for
guessing valid ids (repeatedly POST and watch 404 vs 201). It now always
returns 201 and silently stores NULL for that field instead -- a readable id
is still kept.

Review finding 6: the cap is 20 posts/hour per client IP (was 5, too low for
a workshop room sharing one NAT'd IP), and an attempt only counts against
the cap once the feedback row actually commits -- `check_feedback_rate_limit`
(the check) and `record_feedback_attempt` (the record) are now separate
calls in `fipm.auth`."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fipm.db import SessionLocal
from fipm.models import Feedback

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


def test_feedback_post_unknown_session_and_fip_stores_null_not_404(client):
    bad_session = client.post(
        "/api/feedback", json={"q1": 3, "q2": 3, "q3": 3, "sessionId": "doesnotexist"}
    )
    assert bad_session.status_code == 201
    bad_fip = client.post(
        "/api/feedback", json={"q1": 3, "q2": 3, "q3": 3, "fipId": "doesnotexist"}
    )
    assert bad_fip.status_code == 201

    with SessionLocal() as db:
        rows = db.query(Feedback).filter(Feedback.comment.is_(None)).all()
        # Both rows recorded despite the unknown ids -- but with NULL, not
        # the client-supplied unknown id.
        assert any(r.session_id is None for r in rows)
        assert any(r.fip_id is None for r in rows)


def test_feedback_post_private_fip_stores_null_but_public_fip_is_kept(client, client_factory):
    owner = client_factory()
    _register(owner, "ac05-8-fip-owner@example.com")
    fip = owner.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    ).json()
    fip_id = fip["id"]
    assert fip["visibility"] == "private"

    anon = client_factory()
    private_post = anon.post(
        "/api/feedback",
        json={"q1": 3, "q2": 3, "q3": 3, "comment": "about a private fip", "fipId": fip_id},
    )
    assert private_post.status_code == 201

    owner.patch(f"/api/fips/{fip_id}", json={"visibility": "public"})
    public_post = anon.post(
        "/api/feedback",
        json={"q1": 3, "q2": 3, "q3": 3, "comment": "about a public fip", "fipId": fip_id},
    )
    assert public_post.status_code == 201

    with SessionLocal() as db:
        private_row = db.query(Feedback).filter(Feedback.comment == "about a private fip").one()
        assert private_row.fip_id is None  # unreadable -> NULL, not the real id

        public_row = db.query(Feedback).filter(Feedback.comment == "about a public fip").one()
        assert public_row.fip_id == fip_id  # readable -> kept


def test_feedback_post_rate_limited_after_twenty_per_hour(client):
    for _ in range(20):
        r = client.post("/api/feedback", json={"q1": 3, "q2": 3, "q3": 3})
        assert r.status_code == 201

    twenty_first = client.post("/api/feedback", json={"q1": 3, "q2": 3, "q3": 3})
    assert twenty_first.status_code == 429
    assert "Retry-After" in twenty_first.headers


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


class _FakeClient:
    host = "203.0.113.5"


class _FakeRequest:
    client = _FakeClient()
    headers: dict[str, str] = {}


def test_feedback_rate_limit_check_and_record_are_independent(_reset_rate_limits):
    """Unit-level regression for the check/record split itself (review
    finding 6): calling `check_feedback_rate_limit` alone, without
    `record_feedback_attempt`, never trips the cap no matter how many
    times it's called -- only recorded attempts count."""
    from fipm.auth import (
        FEEDBACK_LIMIT_PER_IP,
        check_feedback_rate_limit,
        client_ip,
        record_feedback_attempt,
    )

    fake_request = _FakeRequest()
    for _ in range(FEEDBACK_LIMIT_PER_IP * 2):
        check_feedback_rate_limit(fake_request)  # must never raise: nothing recorded yet

    ip = client_ip(fake_request)
    for _ in range(FEEDBACK_LIMIT_PER_IP):
        record_feedback_attempt(ip)

    with pytest.raises(HTTPException) as exc_info:
        check_feedback_rate_limit(fake_request)
    assert exc_info.value.status_code == 429
