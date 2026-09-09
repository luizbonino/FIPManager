"""AC1 (spec 05-v1-completion.md §8): GET /api/admin/users 404s for
anonymous and for a signed-in non-admin, and 200s for an admin whose items
carry fipCount/sessionCount/knowledgeModelCount equal to the rows actually
owned; ?q= matches email and display name case-insensitively."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import User

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


def test_admin_users_404_for_anonymous_and_non_admin(client, client_factory):
    anon_resp = client.get("/api/admin/users")
    assert anon_resp.status_code == 404

    non_admin = client_factory()
    _register(non_admin, "ac05-1-nonadmin@example.com")
    non_admin_resp = non_admin.get("/api/admin/users")
    assert non_admin_resp.status_code == 404


def test_admin_users_200_with_accurate_counts_and_search(client_factory):
    admin = client_factory()
    _register(admin, "ac05-1-admin@example.com", "Admin One")
    _promote_to_admin("ac05-1-admin@example.com")

    member = client_factory()
    _register(member, "ac05-1-member@example.com", "Searchable Member")
    member.post("/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}})
    member.post(
        "/api/sessions",
        json={
            "title": "ac05-1 session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )

    r = admin.get("/api/admin/users")
    assert r.status_code == 200
    body = r.json()
    items = {item["email"]: item for item in body["items"]}
    assert "ac05-1-member@example.com" in items
    member_item = items["ac05-1-member@example.com"]
    assert member_item["fipCount"] == 1
    assert member_item["sessionCount"] == 1
    assert member_item["knowledgeModelCount"] == 0
    assert member_item["mustChangePassword"] is False

    q_email = admin.get("/api/admin/users", params={"q": "ac05-1-member"})
    assert q_email.status_code == 200
    assert any(i["email"] == "ac05-1-member@example.com" for i in q_email.json()["items"])

    q_name = admin.get("/api/admin/users", params={"q": "SEARCHABLE"})
    assert q_name.status_code == 200
    assert any(i["email"] == "ac05-1-member@example.com" for i in q_name.json()["items"])
