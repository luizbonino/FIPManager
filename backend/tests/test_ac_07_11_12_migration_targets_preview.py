"""AC11/AC12 (spec 07-mail-and-migration.md §8): fork `test-km`, publish
1.0.0, create a FIP with answers on three questions, then `new-version` ->
1.1.0 with one `en` text edit, one question added, one deleted, one hidden
and one answered question split; publish 1.1.0. `GET .../migration-targets`
lists exactly `1.1.0` with its changelog entry, and `[]` before 1.1.0 was
published. `GET .../migration-preview?to=1.1.0` returns `diffVersion: 1`
with AC11's statuses assigned correctly, the edited question `unchanged`
with `flags: ["text-changed"]`, `counts.decisionsRequired == 2`, and
`orphanReassign.options` holding only unanswered, non-hidden target ids."""

from __future__ import annotations

from _migration_helpers import NEW_SECTIONS, build_scenario  # noqa: F401


def test_migration_targets_empty_before_publish_then_lists_1_1_0(client):
    scenario = build_scenario(client, "mig11", publish_target=False)
    fip_id = scenario["fip_id"]
    km_id = scenario["km_id"]

    before = client.get(f"/api/fips/{fip_id}/migration-targets")
    assert before.status_code == 200, before.text
    assert before.json()["items"] == []

    # `build_scenario(..., publish_target=False)` already called new-version;
    # finish the edit+publish here to exercise the "before -> after" gap.
    get2 = client.get(f"/api/knowledge-models/{km_id}/1.1.0")
    etag2 = get2.headers["etag"]
    put2 = client.put(
        f"/api/knowledge-models/{km_id}/1.1.0/content",
        headers={"If-Match": etag2},
        json={"sections": NEW_SECTIONS},
    )
    assert put2.status_code == 200, put2.text
    pub2 = client.post(
        f"/api/knowledge-models/{km_id}/1.1.0/publish", json={"notes": "release 1.1.0"}
    )
    assert pub2.status_code == 200, pub2.text

    after = client.get(f"/api/fips/{fip_id}/migration-targets")
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["current"] == {"id": km_id, "version": "1.0.0"}
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == km_id
    assert item["version"] == "1.1.0"
    assert len(item["changelog"]) == 1
    assert item["changelog"][0]["version"] == "1.1.0"


def test_migration_preview_statuses_flags_and_counts(client):
    scenario = build_scenario(client, "mig12")
    fip_id = scenario["fip_id"]

    r = client.get(f"/api/fips/{fip_id}/migration-preview?to=1.1.0")
    assert r.status_code == 200, r.text
    diff = r.json()
    assert diff["diffVersion"] == 1
    assert diff["from"]["version"] == "1.0.0"
    assert diff["to"]["version"] == "1.1.0"

    by_old_id = {item["oldQuestionId"]: item for item in diff["items"] if item["oldQuestionId"]}
    assert by_old_id["F1-metadata"]["status"] == "unchanged"
    assert by_old_id["F1-metadata"]["flags"] == ["text-changed"]
    assert by_old_id["F3"]["status"] == "hidden"
    assert by_old_id["F2"]["status"] == "split"
    assert by_old_id["F2"]["splitInto"] == ["F2-metadata", "F2-data"]
    assert by_old_id["A2"]["status"] == "removed"

    added = [item for item in diff["items"] if item["status"] == "added"]
    assert len(added) == 1
    assert added[0]["newQuestionId"] == "R1.3-data"

    assert diff["counts"]["decisionsRequired"] == 2

    removed_decision = by_old_id["A2"]["decision"]
    assert removed_decision["kind"] == "orphanReassign"
    # Only unanswered, non-hidden target ids of the removed question's
    # ferType ("identifier-service") -- F2-metadata/F2-data are
    # metadata-schema and excluded; F1-metadata (unanswered, same ferType)
    # and R1.3-data (added, same ferType) both qualify.
    assert sorted(removed_decision["options"]) == ["F1-metadata", "R1.3-data"]


def test_migration_targets_and_preview_404_for_unknown_fip(client):
    r1 = client.get("/api/fips/doesnotexist/migration-targets")
    assert r1.status_code == 404
    r2 = client.get("/api/fips/doesnotexist/migration-preview?to=1.1.0")
    assert r2.status_code == 404
