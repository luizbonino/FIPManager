"""spec 02-core-flows.md §5.5 / §8 item 6: `Language = Literal["en","pt-PT","pt-BR"]`
applied to session defaultLanguage and FIP language (create + patch) -> 422
on anything else, 200 for an allowed value."""

from __future__ import annotations


def test_session_default_language_rejects_unknown_value(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "lang-session@example.com",
            "password": "correcthorsebattery",
            "displayName": "L",
        },
    )
    bad = client.post(
        "/api/sessions",
        json={
            "title": "t",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "fr",
        },
    )
    assert bad.status_code == 422

    good = client.post(
        "/api/sessions",
        json={
            "title": "t",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "pt-BR",
        },
    )
    assert good.status_code == 201
    session_id = good.json()["id"]

    patch_bad = client.patch(f"/api/sessions/{session_id}", json={"defaultLanguage": "fr"})
    assert patch_bad.status_code == 422

    patch_good = client.patch(f"/api/sessions/{session_id}", json={"defaultLanguage": "pt-PT"})
    assert patch_good.status_code == 200
    assert patch_good.json()["defaultLanguage"] == "pt-PT"

    patch_status_bad = client.patch(f"/api/sessions/{session_id}", json={"status": "archived"})
    assert patch_status_bad.status_code == 422

    patch_status_good = client.patch(f"/api/sessions/{session_id}", json={"status": "open"})
    assert patch_status_good.status_code == 200


def test_fip_language_rejects_unknown_value_on_create_and_patch(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "lang-fip@example.com",
            "password": "correcthorsebattery",
            "displayName": "L",
        },
    )
    bad = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "language": "fr"},
    )
    assert bad.status_code == 422

    good = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "language": "pt-BR"},
    )
    assert good.status_code == 201
    fip_id = good.json()["id"]
    assert good.json()["language"] == "pt-BR"

    patch_bad = client.patch(f"/api/fips/{fip_id}", json={"language": "fr"})
    assert patch_bad.status_code == 422

    patch_good = client.patch(f"/api/fips/{fip_id}", json={"language": "pt-PT"})
    assert patch_good.status_code == 200
    assert patch_good.json()["language"] == "pt-PT"
