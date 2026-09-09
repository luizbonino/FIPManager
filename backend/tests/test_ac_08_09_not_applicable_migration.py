"""spec 08-workshop-picklists.md §6 AC9: migrating a FIP with an N/A answer
to a new model version preserves the flag when the question id persists
(F3, hidden but not removed between the fixture's OLD_SECTIONS/NEW_SECTIONS)
and moves it to `orphanedAnswers` when it does not (A2, dropped entirely)."""

from __future__ import annotations

from tests._migration_helpers import build_scenario


def test_not_applicable_preserved_on_persisting_id_and_orphaned_on_removed_id(client):
    answers = [
        {"questionId": "F3", "notApplicable": True, "comment": "F3 does not apply here"},
        {"questionId": "A2", "notApplicable": True, "comment": "A2 does not apply either"},
    ]
    scenario = build_scenario(client, "ac0809", answers=answers)
    fip_id = scenario["fip_id"]
    new_version = scenario["new_version"]

    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": new_version})
    assert migrate.status_code == 200, migrate.text

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    doc = export.json()

    # F3 persists (now hidden) -- its notApplicable flag survives in
    # `answers`. Hidden questions are skipped by exports (spec 04 §4), so
    # assert via the stored row directly instead of the padded export
    # document.
    from fipm.db import SessionLocal
    from fipm.models import Fip

    with SessionLocal() as db:
        fip = db.get(Fip, fip_id)
        stored_f3 = next(a for a in fip.answers if a["questionId"] == "F3")
        assert stored_f3.get("notApplicable") is True

    # A2 is dropped from the target model -- it moves to orphanedAnswers,
    # flag intact.
    orphaned_a2 = next(o for o in doc["orphanedAnswers"] if o["questionId"] == "A2")
    assert orphaned_a2["notApplicable"] is True
    assert orphaned_a2["comment"] == "A2 does not apply either"
    assert not any(a["questionId"] == "A2" for a in doc["answers"])
