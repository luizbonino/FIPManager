"""Review finding 6: `visibility` (FipCreateRequest/FipPatchRequest) and
session `status` (SessionPatchRequest) are Literal types, so an invalid value
fails Pydantic validation (422) before any handler code runs, instead of
being stored as an arbitrary string."""

from __future__ import annotations


def test_create_fip_rejects_invalid_visibility(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "enum-create@example.com",
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "visibility": "not-a-visibility",
        },
    )
    assert r.status_code == 422


def test_patch_fip_rejects_invalid_visibility(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "enum-patch@example.com",
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    fip_id = created.json()["id"]
    r = client.patch(f"/api/fips/{fip_id}", json={"visibility": "not-a-visibility"})
    assert r.status_code == 422


def test_patch_session_rejects_invalid_status(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "enum-session@example.com",
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = client.post(
        "/api/sessions",
        json={
            "title": "t",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()
    r = client.patch(f"/api/sessions/{session['id']}", json={"status": "OPEN"})
    assert r.status_code == 422
