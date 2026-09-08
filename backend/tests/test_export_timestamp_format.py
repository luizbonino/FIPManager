"""Review finding 11: fip.created_at/updated_at come back from SQLite as
naive datetimes even though the column is DateTime(timezone=True); the export
JSON must attach UTC before isoformat() so createdAt/updatedAt end in "Z"
(matching generatedAt), rather than emitting an ambiguous offset-less string."""

from __future__ import annotations


def test_export_json_timestamps_end_in_z(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "export-tz@example.com",
            "password": "correcthorsebattery",
            "displayName": "TZ",
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    fip_id = created.json()["id"]

    doc = client.get(f"/api/fips/{fip_id}/export.json").json()
    assert doc["fip"]["createdAt"].endswith("Z")
    assert doc["fip"]["updatedAt"].endswith("Z")
    assert "+00:00" not in doc["fip"]["createdAt"]
    assert "+00:00" not in doc["fip"]["updatedAt"]
