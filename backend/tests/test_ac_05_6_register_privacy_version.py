"""AC6 (spec 05-v1-completion.md §8): POST /api/auth/register without
privacyAcceptedVersion returns 422, with a wrong version 400
privacy_version_mismatch, and with the current version 201 -- stored on the
user and echoed by GET /api/auth/me."""

from __future__ import annotations


def test_register_missing_privacy_version_is_422(client):
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac05-6-missing@example.com",
            "password": "correcthorsebattery",
            "displayName": "U",
        },
    )
    assert r.status_code == 422


def test_register_wrong_privacy_version_is_400(client):
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac05-6-wrong@example.com",
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "not-the-current-version",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "privacy_version_mismatch"


def test_register_current_privacy_version_is_stored_and_echoed(client):
    current_version = client.get("/api/privacy").json()["version"]
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac05-6-ok@example.com",
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": current_version,
        },
    )
    assert r.status_code == 201
    assert r.json()["privacyAcceptedVersion"] == current_version

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["privacyAcceptedVersion"] == current_version
