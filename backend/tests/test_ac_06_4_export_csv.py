"""AC5 (spec 06-dmp-linkage.md §5): CSV_HEADER has 24 entries ending
dmp_url, dmp_section, dmp_question, the first 21 unchanged and in order, and
the evidence-carrying declaration's row holds the normalised URL, C and C.3."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER

_ORIGINAL_21 = [
    "fip_id",
    "fip_url",
    "language",
    "license",
    "questionnaire_id",
    "questionnaire_version",
    "community_name",
    "section_id",
    "section_title",
    "question_id",
    "question_text",
    "principle",
    "scope",
    "fer_type",
    "declaration_index",
    "fer_id",
    "fer_label",
    "fer_free_text",
    "status",
    "note",
    "comment",
]


def test_csv_header_24_columns_first_21_unchanged():
    assert len(CSV_HEADER) == 24
    assert CSV_HEADER[:21] == _ORIGINAL_21
    assert CSV_HEADER[21:] == ["dmp_url", "dmp_section", "dmp_question"]


def test_evidence_row_holds_normalised_url_section_and_question(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac5-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "DMP",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    ).json()
    fip_id = created["id"]

    client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [{"url": "https://www.fiodmp.fiocruz.br/publico/kqu5n0c/"}],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "dmpEvidence": {"dmpIndex": 0, "section": "C", "questionRef": "C.3"},
                        }
                    ],
                }
            ],
        },
    )

    export = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export.status_code == 200
    raw = export.content.decode("utf-8-sig")
    lines = [line for line in raw.split("\r\n") if line]
    header = lines[0].split(",")
    assert header == CSV_HEADER

    row = next(line for line in lines[1:] if "F1-metadata" in line)
    cells = row.split(",")
    assert cells[header.index("dmp_url")] == "https://fiodmp.fiocruz.br/KQU5N0C"
    assert cells[header.index("dmp_section")] == "C"
    assert cells[header.index("dmp_question")] == "C.3"
