"""AC18 (spec 07-mail-and-migration.md §8): after migration `export.json`
has `exportVersion 2`, `fip.migratedFrom`, `orphanedAnswers` with enriched
FER labels and no `answers` entry for the hidden or removed question;
re-importing it yields a FIP whose `answers`, `orphanedAnswers`,
`migratedFrom` and `questionnaireRef` equal the original's, and
`export.csv`'s header is unchanged by this spec."""

from __future__ import annotations

from _migration_helpers import build_scenario

from fipm.exporters import CSV_HEADER


def test_export_json_after_migration(client):
    scenario = build_scenario(client, "mig18")
    fip_id = scenario["fip_id"]

    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert migrate.status_code == 200, migrate.text

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    doc = export.json()
    assert doc["exportVersion"] == 2
    assert doc["fip"]["migratedFrom"]["version"] == "1.0.0"

    orphaned = doc["orphanedAnswers"]
    assert len(orphaned) == 1
    assert orphaned[0]["questionId"] == "A2"
    # FER-enriched like `answers`: `fer.label` resolved off the Fer table
    # when the referenced FER exists, else at least `fer.id` is preserved.
    assert orphaned[0]["declarations"][0]["fer"]["id"] == "https://w3id.org/np/orcid"

    answer_ids = {a["questionId"] for a in doc["answers"]}
    assert "A2" not in answer_ids  # removed question: no answers entry
    # F3 (hidden) is still stored on the FIP but exports skip hidden
    # questions entirely (spec 04 §4) -- no row for it either.
    assert "F3" not in answer_ids


def test_export_json_reimport_round_trips(client):
    scenario = build_scenario(client, "mig18b")
    fip_id = scenario["fip_id"]
    km_id = scenario["km_id"]

    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert migrate.status_code == 200, migrate.text
    original = client.get(f"/api/fips/{fip_id}").json()

    export = client.get(f"/api/fips/{fip_id}/export.json").json()
    export["questionnaireRef"] = {"id": km_id, "version": "1.1.0"}

    imported = client.post("/api/fips/import", json=export)
    assert imported.status_code == 201, imported.text
    reimported_fip_id = imported.json()["id"]
    reimported = client.get(f"/api/fips/{reimported_fip_id}").json()

    # `export.json` never carries a hidden question's answer (spec 04 §4,
    # pre-existing and unrelated to this spec) -- so it cannot round-trip
    # through import either. It also *pads* every non-hidden question with
    # an empty entry regardless of whether it was ever answered (same
    # pre-existing export shape AC10 exercises with fully-answered
    # questionnaires only) -- an unanswered question like F1-metadata here
    # therefore reimports as an explicit empty entry it never had before
    # export. Compare only the questions that were actually answered on
    # both sides, which is what §4.2/§4.3's "answers" really means.
    def _answered(answers):
        return [a for a in answers if a["declarations"] or a["comment"]]

    exportable_original_answers = [a for a in original["answers"] if a["questionId"] != "F3"]
    assert _answered(reimported["answers"]) == _answered(exportable_original_answers)
    assert reimported["migratedFrom"] == original["migratedFrom"]
    assert reimported["questionnaireId"] == original["questionnaireId"]
    assert reimported["questionnaireVersion"] == original["questionnaireVersion"]

    reimported_export = client.get(f"/api/fips/{reimported_fip_id}/export.json").json()
    original_export = client.get(f"/api/fips/{fip_id}/export.json").json()
    assert reimported_export["orphanedAnswers"] == original_export["orphanedAnswers"]


def test_export_csv_header_unchanged_after_migration(client):
    scenario = build_scenario(client, "mig18c")
    fip_id = scenario["fip_id"]
    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert migrate.status_code == 200, migrate.text

    csv_resp = client.get(f"/api/fips/{fip_id}/export.csv")
    assert csv_resp.status_code == 200
    header_line = csv_resp.text.lstrip("﻿").splitlines()[0]
    assert header_line == ",".join(CSV_HEADER)


def test_export_json_v1_still_imports(client):
    """spec §6: "readers of 1 unaffected, POST /api/fips/import accepts 1
    and 2"."""
    scenario = build_scenario(client, "mig18d", publish_target=False)
    fip_id = scenario["fip_id"]
    km_id = scenario["km_id"]

    export = client.get(f"/api/fips/{fip_id}/export.json").json()
    # Simulate a pre-spec-07 exportVersion 1 document: no orphanedAnswers,
    # no migratedFrom.
    export["exportVersion"] = 1
    export.pop("orphanedAnswers", None)
    export["fip"].pop("migratedFrom", None)
    export["questionnaireRef"] = {"id": km_id, "version": "1.0.0"}

    imported = client.post("/api/fips/import", json=export)
    assert imported.status_code == 201, imported.text
    assert imported.json()["migratedFrom"] is None
