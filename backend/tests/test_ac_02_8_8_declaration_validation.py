"""spec 02-core-flows.md §8 item 8: PATCH /api/fips/{id} returns 422 for a
declaration carrying both ferId and ferFreeText, for one carrying neither,
and for a status outside the five allowed values; the ferId xor ferFreeText
validator and the status-allowlist validator already exist on
schemas.Declaration (`_fer_xor`, `_status_allowed`) -- this exercises them
through the live PATCH endpoint. With ferFreeText only it returns 200 and
the export shows `ferFreeText` set and `fer` null."""

from __future__ import annotations


def _create_fip(client, email):
    client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "D",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_patch_rejects_declaration_with_both_fer_id_and_free_text(client):
    fip_id = _create_fip(client, "decl-both@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "ferFreeText": "Also my own wording",
                            "status": "current",
                        }
                    ],
                }
            ]
        },
    )
    assert r.status_code == 422


def test_patch_rejects_declaration_with_neither_fer_id_nor_free_text(client):
    fip_id = _create_fip(client, "decl-neither@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={"answers": [{"questionId": "F1-metadata", "declarations": [{"status": "current"}]}]},
    )
    assert r.status_code == 422


def test_patch_rejects_declaration_with_bad_status(client):
    fip_id = _create_fip(client, "decl-bad-status@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferFreeText": "x", "status": "not-a-real-status"}],
                }
            ]
        },
    )
    assert r.status_code == 422


def test_patch_accepts_free_text_only_and_export_shows_fer_null(client):
    fip_id = _create_fip(client, "decl-ok@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferFreeText": "Our in-house registry", "status": "planned"}],
                }
            ]
        },
    )
    assert r.status_code == 200

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    f1_answer = next(a for a in export.json()["answers"] if a["questionId"] == "F1-metadata")
    decl = f1_answer["declarations"][0]
    assert decl["ferFreeText"] == "Our in-house registry"
    assert decl["fer"] is None
