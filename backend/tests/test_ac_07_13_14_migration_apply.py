"""AC13/AC14 (spec 07-mail-and-migration.md §8): `POST .../migrate` with no
`decisions` applies the defaults -- split answer under both new ids,
deleted question's answer in `orphanedAnswers` with `fromVersion "1.0.0"`,
`questionnaireRef.version == "1.1.0"`, `migratedFrom == {"id", "version":
"1.0.0", "at"}`, hidden question's answer still in `answers`.
`splitCopies {"F2": ["F2-metadata"]}` puts the answer on `F2-metadata` only
and not in `orphanedAnswers`; an empty list orphans it; `orphanReassign
{"A2": "A2-data"}`-equivalent (here `R1.3-data`, the only valid option)
puts the declarations there and still records the `orphanedAnswers`
entry."""

from __future__ import annotations

from _migration_helpers import build_scenario


def test_migrate_with_no_decisions_applies_defaults(client):
    scenario = build_scenario(client, "mig13")
    fip_id = scenario["fip_id"]
    km_id = scenario["km_id"]

    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["questionnaireVersion"] == "1.1.0"
    assert body["questionnaireId"] == km_id
    assert body["migratedFrom"] == {
        "id": km_id,
        "version": "1.0.0",
        "at": body["migratedFrom"]["at"],
    }

    answers_by_id = {a["questionId"]: a for a in body["answers"]}
    assert "F2-metadata" in answers_by_id
    assert "F2-data" in answers_by_id
    assert "F3" in answers_by_id  # hidden question's answer stays in answers
    assert "A2" not in answers_by_id

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    orphaned = export.json()["orphanedAnswers"]
    assert len(orphaned) == 1
    assert orphaned[0]["questionId"] == "A2"
    assert orphaned[0]["fromVersion"] == "1.0.0"


def test_migrate_split_copies_and_orphan_reassign_decisions(client):
    scenario = build_scenario(client, "mig14")
    fip_id = scenario["fip_id"]

    r = client.post(
        f"/api/fips/{fip_id}/migrate",
        json={
            "to": "1.1.0",
            "decisions": {
                "splitCopies": {"F2": ["F2-metadata"]},
                "orphanReassign": {"A2": "R1.3-data"},
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    answers_by_id = {a["questionId"]: a for a in body["answers"]}
    assert "F2-metadata" in answers_by_id
    assert "F2-data" not in answers_by_id
    assert "R1.3-data" in answers_by_id
    assert answers_by_id["R1.3-data"]["declarations"][0]["ferId"] == "https://w3id.org/np/orcid"

    export = client.get(f"/api/fips/{fip_id}/export.json").json()
    orphaned_ids = {o["questionId"] for o in export["orphanedAnswers"]}
    # AC14: an orphanReassign target still records the orphanedAnswers entry.
    assert "A2" in orphaned_ids
    assert "F2" not in orphaned_ids  # non-empty splitCopies -> not orphaned


def test_migrate_empty_split_list_orphans_the_answer(client):
    scenario = build_scenario(client, "mig14b")
    fip_id = scenario["fip_id"]

    r = client.post(
        f"/api/fips/{fip_id}/migrate",
        json={"to": "1.1.0", "decisions": {"splitCopies": {"F2": []}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    answers_by_id = {a["questionId"]: a for a in body["answers"]}
    assert "F2-metadata" not in answers_by_id
    assert "F2-data" not in answers_by_id

    export = client.get(f"/api/fips/{fip_id}/export.json").json()
    orphaned_ids = {o["questionId"] for o in export["orphanedAnswers"]}
    assert "F2" in orphaned_ids
