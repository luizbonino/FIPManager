"""AC12: a state-changing request without Origin/Referer, or with a foreign
Origin, returns 403 csrf_failed; the same request with the app's own Origin
succeeds. GET requests are unaffected."""

from __future__ import annotations


def test_csrf_rejected_without_origin_and_with_foreign_origin(raw_client, settings):
    no_origin = raw_client.post(
        "/api/auth/register",
        json={"email": "ac12-a@example.com", "password": "correcthorsebattery", "displayName": "A"},
    )
    assert no_origin.status_code == 403
    assert no_origin.json()["detail"] == "csrf_failed"

    foreign_origin = raw_client.post(
        "/api/auth/register",
        json={"email": "ac12-b@example.com", "password": "correcthorsebattery", "displayName": "B"},
        headers={"origin": "https://evil.example.com"},
    )
    assert foreign_origin.status_code == 403
    assert foreign_origin.json()["detail"] == "csrf_failed"

    same_origin = raw_client.post(
        "/api/auth/register",
        json={"email": "ac12-c@example.com", "password": "correcthorsebattery", "displayName": "C"},
        headers={"origin": settings.base_url},
    )
    assert same_origin.status_code == 201


def test_csrf_does_not_affect_get(raw_client):
    r = raw_client.get("/api/health")
    assert r.status_code == 200
