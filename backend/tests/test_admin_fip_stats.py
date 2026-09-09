"""spec 09-standalone-fips.md retention runbook: GET /api/admin/stats reports
`ownedFips`/`standaloneFips`/`sessionFips` counts (spec 09 §2's authorization
table kinds), 404 for anonymous/non-admin like every other /api/admin/* route
(spec 01 §5's leak rule)."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import User

QREF = {"id": "test-km", "version": "1.0.0"}
PRIVACY_VERSION = "test-v1"


def _register(client, email, display_name="U"):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": display_name,
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _promote_to_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()


def test_stats_404_for_anonymous_and_non_admin(client, client_factory):
    anon = client.get("/api/admin/stats")
    assert anon.status_code == 404

    non_admin = client_factory()
    _register(non_admin, "admin-stats-nonadmin@example.com")
    r = non_admin.get("/api/admin/stats")
    assert r.status_code == 404


def test_stats_counts_by_kind(client, client_factory):
    admin = client_factory()
    _register(admin, "admin-stats-admin@example.com", "Admin")
    _promote_to_admin("admin-stats-admin@example.com")

    before = admin.get("/api/admin/stats")
    assert before.status_code == 200, before.text
    base = before.json()

    # Owned: owner_id set.
    owner = client_factory()
    _register(owner, "admin-stats-owner@example.com")
    owned = owner.post("/api/fips", json={"questionnaireRef": QREF})
    assert owned.status_code == 201, owned.text

    # Standalone: owner_id and session_id both NULL.
    standalone = client.post("/api/fips", json={"questionnaireRef": QREF})
    assert standalone.status_code == 201, standalone.text

    # Session (anonymous): owner_id NULL, session_id set.
    facilitator = client_factory()
    _register(facilitator, "admin-stats-facilitator@example.com")
    session_r = facilitator.post(
        "/api/sessions",
        json={"title": "stats session", "questionnaireRef": QREF, "defaultLanguage": "en"},
    )
    assert session_r.status_code == 201, session_r.text
    session = session_r.json()
    session_fip = client.post(
        "/api/fips",
        json={
            "questionnaireRef": QREF,
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert session_fip.status_code == 201, session_fip.text

    after = admin.get("/api/admin/stats")
    assert after.status_code == 200, after.text
    data = after.json()
    assert data["ownedFips"] == base["ownedFips"] + 1
    assert data["standaloneFips"] == base["standaloneFips"] + 1
    assert data["sessionFips"] == base["sessionFips"] + 1
