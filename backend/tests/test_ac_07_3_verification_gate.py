"""AC3 (spec 07-mail-and-migration.md §7): with
`FIPM_REQUIRE_EMAIL_VERIFICATION=true` an unverified user gets 403
`email_verification_required` from `POST /api/fips` with `visibility="public"`
and from a `PATCH` to `public`, but 201/200 for `private`/`link` and may
create and answer a session; after verification the public write succeeds.
With the flag `false` (the suite's default elsewhere) nothing is blocked.

Uses `fipm.config.get_settings.cache_clear()` + monkeypatch of the env var,
scoped to each test via a fixture that restores the flag afterwards -- the
setting is read fresh (`get_settings()` is `lru_cache`d) by every request."""

from __future__ import annotations

import re

import pytest

from fipm.config import get_settings

PRIVACY_VERSION = "test-v1"


@pytest.fixture()
def require_verification(monkeypatch):
    monkeypatch.setenv("FIPM_REQUIRE_EMAIL_VERIFICATION", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("FIPM_REQUIRE_EMAIL_VERIFICATION", raising=False)
    get_settings.cache_clear()


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "G",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_unverified_user_blocked_from_public_but_not_private_or_link(
    client, require_verification, caplog
):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-gate-a@example.com")

    r_public = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "visibility": "public",
        },
    )
    assert r_public.status_code == 403
    assert r_public.json()["detail"] == "email_verification_required"

    r_private = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "visibility": "private",
        },
    )
    assert r_private.status_code == 201, r_private.text

    r_link = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "visibility": "link"},
    )
    assert r_link.status_code == 201, r_link.text

    fip_id = r_private.json()["id"]
    r_patch_public = client.patch(f"/api/fips/{fip_id}", json={"visibility": "public"})
    assert r_patch_public.status_code == 403
    assert r_patch_public.json()["detail"] == "email_verification_required"

    r_patch_link = client.patch(f"/api/fips/{fip_id}", json={"visibility": "link"})
    assert r_patch_link.status_code == 200, r_patch_link.text


def test_unverified_user_may_create_and_join_a_session(client, require_verification):
    _register(client, "ac07-gate-session@example.com")
    session_r = client.post(
        "/api/sessions",
        json={
            "title": "Gate session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert session_r.status_code == 201, session_r.text


def test_after_verification_public_write_succeeds(client, require_verification, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-gate-b@example.com")
    message = next(r for r in caplog.records if r.name == "fipm.mail").getMessage()
    token = re.search(r"/verify\?token=(\S+)", message).group(1)
    verify = client.post("/api/auth/verify-email", json={"token": token})
    assert verify.status_code == 200

    r_public = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "visibility": "public",
        },
    )
    assert r_public.status_code == 201, r_public.text


def test_import_fip_rejects_public_when_unverified(client, require_verification):
    """Audit finding 3: POST /fips/import used to skip
    `check_email_verification_gate` entirely, so an unverified user could
    import straight into `visibility="public"` -- the one write path every
    other FIP-creating endpoint (POST /fips, PATCH /fips/{id}) already
    gates."""
    _register(client, "ac07-gate-import@example.com")
    doc = {
        "exportVersion": 1,
        "fip": {"visibility": "public"},
        "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        "answers": [],
    }
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 403
    assert r.json()["detail"] == "email_verification_required"


def test_flag_false_blocks_nothing(client):
    """The suite's default elsewhere (flag off) -- spec 01-06 test changes
    would be a regression, so this is the control case."""
    _register(client, "ac07-gate-flag-off@example.com")
    r_public = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "visibility": "public",
        },
    )
    assert r_public.status_code == 201, r_public.text
