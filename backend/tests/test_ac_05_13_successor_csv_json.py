"""AC13 (spec 05-v1-completion.md §8): export.csv's header is exactly the 21
spec-01 columns plus dmp_url/dmp_section/dmp_question plus successor_fer_id/
successor_fer_label (26; session CSV 28), the label resolves in the FIP's
language, and export.json -> POST /api/fips/import round-trips both
successor fields."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER, SESSION_CSV_HEADER

PRIVACY_VERSION = "test-v1"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_csv_and_session_csv_header_lengths():
    assert len(CSV_HEADER) == 26
    assert CSV_HEADER[-2:] == ["successor_fer_id", "successor_fer_label"]
    assert len(SESSION_CSV_HEADER) == 28
    assert SESSION_CSV_HEADER[-2:] == ["successor_fer_id", "successor_fer_label"]


def test_successor_label_resolves_in_fip_language_and_csv_carries_it(client):
    _register(client, "ac05-13-user@example.com")
    successor_fer = client.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-13-successor",
            "label": {"en": "New Registry EN", "pt-BR": "Novo Registro PT"},
            "type": "metadata-schema",
        },
    ).json()

    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "language": "pt-BR",
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "planned-replacement",
                            "successorFerId": successor_fer["id"],
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 201
    fip_id = created.json()["id"]

    export_json = client.get(f"/api/fips/{fip_id}/export.json").json()
    decl = next(a for a in export_json["answers"] if a["questionId"] == "F1-metadata")[
        "declarations"
    ][0]
    assert decl["successor"]["id"] == successor_fer["id"]
    assert decl["successor"]["label"] == "Novo Registro PT"
    assert decl["successorFreeText"] is None

    export_csv = client.get(f"/api/fips/{fip_id}/export.csv")
    raw = export_csv.content.decode("utf-8-sig")
    lines = [line for line in raw.split("\r\n") if line]
    header = lines[0].split(",")
    assert header == CSV_HEADER
    row = next(line for line in lines[1:] if "F1-metadata" in line).split(",")
    assert row[header.index("successor_fer_id")] == successor_fer["id"]
    assert row[header.index("successor_fer_label")] == "Novo Registro PT"


def test_successor_free_text_label_falls_back_and_import_round_trips(client):
    _register(client, "ac05-13-freetext@example.com")
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "planned-replacement",
                            "successorFreeText": "Our own replacement tool",
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 201
    fip_id = created.json()["id"]

    export_csv = client.get(f"/api/fips/{fip_id}/export.csv")
    raw = export_csv.content.decode("utf-8-sig")
    lines = [line for line in raw.split("\r\n") if line]
    header = lines[0].split(",")
    row = next(line for line in lines[1:] if "F1-metadata" in line).split(",")
    assert row[header.index("successor_fer_id")] == ""
    assert row[header.index("successor_fer_label")] == "Our own replacement tool"

    export_json = client.get(f"/api/fips/{fip_id}/export.json").json()
    imported = client.post(
        "/api/fips/import",
        json={
            "exportVersion": 1,
            "fip": export_json["fip"],
            "questionnaireRef": export_json["questionnaireRef"],
            "answers": export_json["answers"],
        },
    )
    assert imported.status_code == 201
    imported_body = imported.json()
    decl = next(a for a in imported_body["answers"] if a["questionId"] == "F1-metadata")[
        "declarations"
    ][0]
    assert decl["successorFreeText"] == "Our own replacement tool"
    assert decl["ferId"] == "https://w3id.org/np/doi"
