"""AC11: GET /fips/{id}/export.csv returns text/csv with the exact 26-column
§3.2 header (spec 06-dmp-linkage.md §2.4 appended dmp_url/dmp_section/
dmp_question; spec 05-v1-completion.md §5 then appended successor_fer_id/
successor_fer_label), one row per declaration, and one row for each
unanswered question."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER


def test_export_csv_header_and_rows(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "ac11-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "AC11",
            "privacyAcceptedVersion": "test-v1",
        },
    )

    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [
                {"ferId": "https://w3id.org/np/doi", "status": "current"},
                {"ferFreeText": "Another identifier service", "status": "planned"},
            ],
            "comment": "two declarations",
        }
        # F2 intentionally left unanswered.
    ]
    created = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "answers": answers},
    )
    assert created.status_code == 201
    fip_id = created.json()["id"]

    export = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")

    raw = export.content.decode("utf-8-sig")
    lines = raw.split("\r\n")
    header = lines[0].split(",")
    assert header == CSV_HEADER
    assert len(header) == 26

    data_lines = [line for line in lines[1:] if line]
    # 2 declarations for F1-metadata + 1 row for the unanswered F2 = 3 rows.
    assert len(data_lines) == 3
