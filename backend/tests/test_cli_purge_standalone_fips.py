"""spec 09-standalone-fips.md retention runbook: `python -m fipm
purge-standalone-fips` deletes a standalone FIP (owner_id AND session_id both
NULL) whose `updated_at` is older than `--older-than-days`; `--dry-run`
counts without deleting; owned and session-anonymous FIPs are never touched
regardless of age."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fipm.cli import main
from fipm.db import SessionLocal
from fipm.models import Fip

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


def _age_fip(fip_id: str, days: int) -> None:
    with SessionLocal() as db:
        fip = db.get(Fip, fip_id)
        fip.updated_at = datetime.now(UTC) - timedelta(days=days)
        db.commit()


def _exists(fip_id: str) -> bool:
    with SessionLocal() as db:
        return db.get(Fip, fip_id) is not None


def test_dry_run_counts_but_does_not_delete(client, capsys):
    fip = client.post("/api/fips", json={"questionnaireRef": QREF}).json()
    fip_id = fip["id"]
    _age_fip(fip_id, 400)

    exit_code = main(["purge-standalone-fips", "--older-than-days", "365", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "would purge" in out
    assert _exists(fip_id)


def test_purge_deletes_old_standalone_fip(client, capsys):
    fip = client.post("/api/fips", json={"questionnaireRef": QREF}).json()
    fip_id = fip["id"]
    _age_fip(fip_id, 400)

    exit_code = main(["purge-standalone-fips", "--older-than-days", "365"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "purged" in out
    assert not _exists(fip_id)


def test_purge_leaves_recently_edited_standalone_fip(client):
    fip = client.post("/api/fips", json={"questionnaireRef": QREF}).json()
    fip_id = fip["id"]
    # updated_at defaults to "now" on creation -- well inside the 365-day
    # window, so the age filter (not just the owner/session filter) must
    # exclude it.

    main(["purge-standalone-fips", "--older-than-days", "365"])

    assert _exists(fip_id)


def test_purge_never_touches_owned_or_session_fips_even_when_old(client, client_factory):
    owner = client_factory()
    _register(owner, "cli-purge-owner@example.com")
    owned_fip = owner.post("/api/fips", json={"questionnaireRef": QREF}).json()
    _age_fip(owned_fip["id"], 400)

    facilitator = client_factory()
    _register(facilitator, "cli-purge-facilitator@example.com")
    session_r = facilitator.post(
        "/api/sessions",
        json={"title": "cli-purge session", "questionnaireRef": QREF, "defaultLanguage": "en"},
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
    ).json()
    _age_fip(session_fip["id"], 400)

    main(["purge-standalone-fips", "--older-than-days", "365"])

    assert _exists(owned_fip["id"])
    assert _exists(session_fip["id"])
