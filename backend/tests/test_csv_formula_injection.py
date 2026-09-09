"""Review finding 1: CSV/spreadsheet formula injection. A community name
starting with `=` (or `+`, `-`, `@`, tab, CR) must be prefixed with a single
quote in every CSV cell it lands in — both the single-FIP export and the
session-wide export — so spreadsheet apps render it as text rather than
evaluating it as a formula."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER, SESSION_CSV_HEADER

MALICIOUS_NAME = "=cmd|' /C calc'!A0"


def test_fip_export_csv_escapes_formula_injection(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "csvinj-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "CSVInj",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "community": {"name": MALICIOUS_NAME},
        },
    )
    assert created.status_code == 201
    fip_id = created.json()["id"]

    export = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export.status_code == 200
    raw = export.content.decode("utf-8-sig")
    lines = raw.split("\r\n")
    data_lines = [line for line in lines[1:] if line]
    assert data_lines

    community_idx = CSV_HEADER.index("community_name")
    for line in data_lines:
        cell = line.split(",")[community_idx]
        assert cell == "'" + MALICIOUS_NAME
        assert not cell.startswith("=")


def test_session_export_csv_escapes_formula_injection(client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "csvinj-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "csv injection session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "community": {"name": MALICIOUS_NAME},
        },
    )
    assert created.status_code == 201

    export = owner.get(f"/api/sessions/{session['id']}/export.csv")
    assert export.status_code == 200
    raw = export.content.decode("utf-8-sig")
    lines = raw.split("\r\n")
    data_lines = [line for line in lines[1:] if line]
    assert data_lines

    fip_title_idx = SESSION_CSV_HEADER.index("fip_title")
    community_idx = SESSION_CSV_HEADER.index("community_name")
    for line in data_lines:
        cells = line.split(",")
        assert cells[fip_title_idx] == "'" + MALICIOUS_NAME
        assert cells[community_idx] == "'" + MALICIOUS_NAME
