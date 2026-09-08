"""AC13: GET /api/health returns 200 with no auth and no cookie required."""

from __future__ import annotations


def test_health_no_auth_required(raw_client):
    r = raw_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "schemaVersion" in body
    assert "time" in body
    assert "fipm_session" not in r.cookies
