"""spec 08-workshop-picklists.md §6 AC8: a FIP with one N/A answer exports:
JSON with `notApplicable: true` and `declarations: []`; CSV with exactly one
row for that question, `status == "not-applicable"` and the declaration/dmp/
successor columns empty; Turtle containing `fipmx:not-applicable true` on
`#answer-<qid>` and no `fip:FIP-Declaration`, `fipmx:has-declaration` or
`declares-*` triple for it. `POST /api/fips/import` of that JSON reproduces
the flag."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER


def _create_fip_with_na_answer(client, email):
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
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "notApplicable": True,
                    "comment": "Não coletamos dados primários.",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_json_export_has_not_applicable_true_and_empty_declarations(client):
    fip_id = _create_fip_with_na_answer(client, "ac08-08-json@example.com")
    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    answer = next(a for a in export.json()["answers"] if a["questionId"] == "F1-metadata")
    assert answer["notApplicable"] is True
    assert answer["declarations"] == []


def test_csv_export_has_not_applicable_status_and_empty_named_columns(client):
    fip_id = _create_fip_with_na_answer(client, "ac08-08-csv@example.com")
    export = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export.status_code == 200
    raw = export.content.decode("utf-8-sig")
    lines = [line for line in raw.split("\r\n") if line]
    header = lines[0].split(",")
    assert header == CSV_HEADER

    rows_for_q = [
        dict(zip(header, line.split(","), strict=True))
        for line in lines[1:]
        if line.split(",")[header.index("question_id")] == "F1-metadata"
    ]
    assert len(rows_for_q) == 1
    row = rows_for_q[0]
    assert row["status"] == "not-applicable"
    for col in (
        "declaration_index",
        "fer_id",
        "fer_label",
        "fer_free_text",
        "note",
        "dmp_url",
        "dmp_section",
        "dmp_question",
        "successor_fer_id",
        "successor_fer_label",
    ):
        assert row[col] == "", (col, row)
    assert row["comment"] == "Não coletamos dados primários."


def test_ttl_export_has_not_applicable_triple_and_no_declaration(client):
    fip_id = _create_fip_with_na_answer(client, "ac08-08-ttl@example.com")
    export = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert export.status_code == 200
    ttl = export.content.decode("utf-8")
    assert "fipmx:not-applicable true" in ttl
    assert "fip:FIP-Declaration" not in ttl
    assert "fipmx:has-declaration" not in ttl
    assert "declares-current-use-of" not in ttl
    assert "declares-planned-use-of" not in ttl
    assert "declares-planned-development-of" not in ttl
    assert "declares-planned-replacement-of" not in ttl
    # the answer node itself is still emitted, with its comment.
    assert "fipmx:answer-comment" in ttl


def test_import_reproduces_not_applicable_flag(client):
    fip_id = _create_fip_with_na_answer(client, "ac08-08-import@example.com")
    export = client.get(f"/api/fips/{fip_id}/export.json").json()

    reimported = client.post("/api/fips/import", json=export)
    assert reimported.status_code == 201, reimported.text
    reimported_id = reimported.json()["id"]

    reexport = client.get(f"/api/fips/{reimported_id}/export.json")
    assert reexport.status_code == 200
    answer = next(a for a in reexport.json()["answers"] if a["questionId"] == "F1-metadata")
    assert answer["notApplicable"] is True
    assert answer["declarations"] == []
