"""Review finding 6: owner-only session routes (GET/PATCH /sessions/{id},
GET .../fips, GET .../export.json, GET .../export.csv) must accept the
session owner OR an admin (spec 01-foundations.md), not owner-only. A
non-owner, non-admin user still gets 404."""

from __future__ import annotations

from fipm.models import User


def test_admin_can_access_session_they_do_not_own(client, client_factory, db_session):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "sessadmin-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "Owner",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "admin access",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    admin = client_factory()
    reg = admin.post(
        "/api/auth/register",
        json={
            "email": "sessadmin-admin@example.com",
            "password": "correcthorsebattery",
            "displayName": "Admin",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    admin_id = reg.json()["id"]
    db_session.query(User).filter(User.id == admin_id).update({"role": "admin"})
    db_session.commit()

    assert admin.get(f"/api/sessions/{session['id']}").status_code == 200
    renamed = admin.patch(f"/api/sessions/{session['id']}", json={"title": "renamed by admin"})
    assert renamed.status_code == 200
    assert admin.get(f"/api/sessions/{session['id']}/fips").status_code == 200
    assert admin.get(f"/api/sessions/{session['id']}/export.json").status_code == 200
    assert admin.get(f"/api/sessions/{session['id']}/export.csv").status_code == 200

    # A non-owner, non-admin user still gets 404.
    stranger = client_factory()
    stranger.post(
        "/api/auth/register",
        json={
            "email": "sessadmin-stranger@example.com",
            "password": "correcthorsebattery",
            "displayName": "Stranger",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert stranger.get(f"/api/sessions/{session['id']}").status_code == 404
