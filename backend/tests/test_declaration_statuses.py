"""Coordinator follow-up: DECLARATION_STATUSES is final and "planned" replaces
the earlier draft value "planned-use"."""

from __future__ import annotations

from fipm.config import DECLARATION_STATUSES


def test_declaration_statuses_tuple_is_final():
    assert DECLARATION_STATUSES == (
        "current",
        "planned",
        "planned-development",
        "planned-replacement",
        "none",
    )
    assert "planned-use" not in DECLARATION_STATUSES


def test_fip_creation_rejects_old_planned_use_status(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "status-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "S",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferFreeText": "x", "status": "planned-use"}],
                }
            ],
        },
    )
    assert r.status_code == 422
