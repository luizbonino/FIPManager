"""Spec 09-standalone-fips.md: POST /fips with neither `sessionId` nor a
signed-in cookie -- "anyone can fill a FIP independently, without a
workshop session or an account". Covers: anonymous creation (edit token,
ownerless, sessionless, default visibility "link"), the `private`
rejection, edit-token PATCH auth, anonymous GET, claiming into an account,
JSON/CSV/TTL exports, the `FIPM_ANONYMOUS_FIPS` kill switch, and the
per-IP rate limit."""

from __future__ import annotations

import pytest

from fipm.config import get_settings
from fipm.exporters import CSV_HEADER

QREF = {"id": "test-km", "version": "1.0.0"}


def _create_standalone(client, **extra):
    body = {"questionnaireRef": QREF, **extra}
    return client.post("/api/fips", json=body)


def test_anonymous_creation_without_session(client):
    r = _create_standalone(client)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["ownerId"] is None
    assert data["sessionId"] is None
    assert data["visibility"] == "link"
    assert data["editToken"]


def test_private_visibility_rejected_for_anonymous_caller(client):
    r = _create_standalone(client, visibility="private")
    assert r.status_code == 400
    assert r.json()["detail"] == "private_requires_account"


def test_public_visibility_allowed_for_anonymous_caller(client):
    r = _create_standalone(client, visibility="public")
    assert r.status_code == 201, r.text
    assert r.json()["visibility"] == "public"


def test_patch_requires_edit_token(client):
    fip = _create_standalone(client).json()
    fip_id, token = fip["id"], fip["editToken"]

    no_token = client.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert no_token.status_code == 403
    assert no_token.json()["detail"] == "edit_token_required"

    wrong_token = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": "nope"}
    )
    assert wrong_token.status_code == 403

    ok = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": token}
    )
    assert ok.status_code == 200
    assert ok.json()["license"] == "MIT"


def test_get_readable_anonymously(client):
    fip = _create_standalone(client).json()
    r = client.get(f"/api/fips/{fip['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == fip["id"]
    assert "editToken" not in r.json()


def test_claim_by_signed_in_user_then_token_stops_working(client, client_factory):
    fip = _create_standalone(client).json()
    fip_id, token = fip["id"], fip["editToken"]

    claimant = client_factory()
    claimant.post(
        "/api/auth/register",
        json={
            "email": "standalone-claimant@example.com",
            "password": "correcthorsebattery",
            "displayName": "Claimant",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    claimed = claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": token})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["ownerId"]
    assert claimed.json()["sessionId"] is None

    stale = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": token}
    )
    assert stale.status_code == 403

    owner_patch = claimant.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert owner_patch.status_code == 200


def test_exports_work_for_standalone_fip(client):
    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
        }
    ]
    fip = _create_standalone(client, answers=answers).json()
    fip_id = fip["id"]

    json_resp = client.get(f"/api/fips/{fip_id}/export.json")
    assert json_resp.status_code == 200
    assert json_resp.json()["fip"]["id"] == fip_id

    csv_resp = client.get(f"/api/fips/{fip_id}/export.csv")
    assert csv_resp.status_code == 200
    assert CSV_HEADER[0] in csv_resp.text

    ttl_resp = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert ttl_resp.status_code == 200
    assert fip_id in ttl_resp.text


@pytest.fixture()
def anonymous_fips_disabled(monkeypatch):
    """`fipm.config.get_settings()` is process-wide `lru_cache`d, so the env
    var must be set and the cache cleared, same pattern as
    test_ac_07_3_verification_gate.py."""
    monkeypatch.setenv("FIPM_ANONYMOUS_FIPS", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_anonymous_fips_disabled_returns_403(client, anonymous_fips_disabled):
    r = _create_standalone(client)
    assert r.status_code == 403
    assert r.json()["detail"] == "anonymous_fips_disabled"


@pytest.fixture()
def small_anonymous_fip_rate_limit(monkeypatch):
    """A tight per-IP cap for this test, so the 31st-creation scenario
    doesn't require 30 real requests: `fipm.auth.check_anonymous_fip_
    rate_limit` reads the module-level constants by name at call time, so
    patching them here is enough."""
    import fipm.auth as auth_module

    monkeypatch.setattr(auth_module, "ANONYMOUS_FIP_LIMIT_PER_IP", 2)
    yield


def test_rate_limit_exceeded_returns_429(client, small_anonymous_fip_rate_limit):
    first = _create_standalone(client)
    assert first.status_code == 201
    second = _create_standalone(client)
    assert second.status_code == 201
    third = _create_standalone(client)
    assert third.status_code == 429
    assert third.json()["detail"] == "rate_limited"
    assert "Retry-After" in third.headers


def test_session_join_and_signed_in_creation_exempt_from_anonymous_rate_limit(
    client, client_factory, small_anonymous_fip_rate_limit
):
    """`fipm.auth.check_anonymous_fip_rate_limit` is only ever called from
    `create_fip`'s fully-anonymous-standalone branch (spec 09 §4: "Only this
    branch is limited -- a session participant ... or a signed-in user,
    never hits it"). All requests below share one client IP (the test
    process), so exhausting the (monkeypatched-to-2) anonymous cap first and
    then still getting 201s from the session-join and signed-in paths is
    proof the limiter key doesn't gate them, not just an artifact of a fresh
    bucket."""
    first = _create_standalone(client)
    assert first.status_code == 201, first.text
    second = _create_standalone(client)
    assert second.status_code == 201, second.text
    exhausted = _create_standalone(client)
    assert exhausted.status_code == 429, exhausted.text

    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "standalone-rl-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "Facilitator",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session_r = facilitator.post(
        "/api/sessions",
        json={
            "title": "rate-limit-exempt session",
            "questionnaireRef": QREF,
            "defaultLanguage": "en",
        },
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

    signed_in = client_factory()
    signed_in.post(
        "/api/auth/register",
        json={
            "email": "standalone-rl-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "Signed-in creator",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    signed_in_fip = signed_in.post("/api/fips", json={"questionnaireRef": QREF})
    assert signed_in_fip.status_code == 201, signed_in_fip.text


def test_delete_requires_edit_token(client):
    fip = _create_standalone(client).json()
    fip_id, token = fip["id"], fip["editToken"]

    no_token = client.delete(f"/api/fips/{fip_id}")
    assert no_token.status_code == 403
    assert no_token.json()["detail"] == "edit_token_required"

    wrong_token = client.delete(f"/api/fips/{fip_id}", headers={"X-Edit-Token": "nope"})
    assert wrong_token.status_code == 403

    ok = client.delete(f"/api/fips/{fip_id}", headers={"X-Edit-Token": token})
    assert ok.status_code == 204

    gone = client.get(f"/api/fips/{fip_id}")
    assert gone.status_code == 404


def test_patch_private_visibility_rejected_for_standalone_fip(client):
    fip = _create_standalone(client).json()
    fip_id, token = fip["id"], fip["editToken"]

    r = client.patch(
        f"/api/fips/{fip_id}",
        json={"visibility": "private"},
        headers={"X-Edit-Token": token},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "private_requires_account"


def test_patch_private_visibility_rejected_for_session_fip(client, client_factory):
    """spec 09-standalone-fips.md §1: the `private_requires_account` rule on
    `PATCH` applies to a session-anonymous FIP too (`owner_id IS NULL`),
    same reasoning as a standalone FIP -- no owner means nobody but the
    token holder could ever read it back."""
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "standalone-patch-private-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "Facilitator",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session_r = facilitator.post(
        "/api/sessions",
        json={
            "title": "patch-private session",
            "questionnaireRef": QREF,
            "defaultLanguage": "en",
        },
    )
    assert session_r.status_code == 201, session_r.text
    session = session_r.json()

    fip_r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": QREF,
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert fip_r.status_code == 201, fip_r.text
    fip = fip_r.json()

    r = client.patch(
        f"/api/fips/{fip['id']}",
        json={"visibility": "private"},
        headers={"X-Edit-Token": fip["editToken"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "private_requires_account"
