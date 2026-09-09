"""AC15 (spec 07-mail-and-migration.md §8): current version -> 409
`already_on_version`; a lower published version -> 400 `version_not_greater`;
another/nonexistent model version -> 404 `target_not_found`; a decision key
on an `unchanged` question -> 400 `unknown_decision`; an `orphanReassign`
target that is hidden or already answered -> 400 `invalid_decision`. In
every rejected case the FIP row is unchanged (same `updated_at`).

Assumption (see builder report): a *draft* (unpublished) target version is
treated as `target_not_found` (404), matching the §4.3 endpoint table's
"unreadable/absent/non-published target -> 404" rule used for both preview
and migrate."""

from __future__ import annotations

from _migration_helpers import build_scenario


def _updated_at(client, fip_id):
    return client.get(f"/api/fips/{fip_id}").json()["updatedAt"]


def test_current_version_is_already_on_version(client):
    scenario = build_scenario(client, "mig15a")
    fip_id = scenario["fip_id"]
    before = _updated_at(client, fip_id)

    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.0.0"})
    assert r.status_code == 409
    assert r.json()["detail"] == "already_on_version"
    assert _updated_at(client, fip_id) == before


def test_lower_published_version_is_version_not_greater(client):
    scenario = build_scenario(client, "mig15b")
    fip_id = scenario["fip_id"]

    # Migrate 1.0.0 -> 1.1.0 first (both published), then attempt to
    # migrate the now-1.1.0 FIP back down to the still-published 1.0.0.
    first = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert first.status_code == 200, first.text
    before = _updated_at(client, fip_id)

    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.0.0"})
    assert r.status_code == 400
    assert r.json()["detail"] == "version_not_greater"
    assert _updated_at(client, fip_id) == before


def test_draft_target_is_target_not_found(client):
    scenario = build_scenario(client, "mig15c", publish_target=False)
    fip_id = scenario["fip_id"]
    before = _updated_at(client, fip_id)

    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert r.status_code == 404
    assert r.json()["detail"] == "target_not_found"
    assert _updated_at(client, fip_id) == before


def test_nonexistent_version_is_target_not_found(client):
    scenario = build_scenario(client, "mig15d")
    fip_id = scenario["fip_id"]
    before = _updated_at(client, fip_id)

    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "9.9.9"})
    assert r.status_code == 404
    assert r.json()["detail"] == "target_not_found"
    assert _updated_at(client, fip_id) == before


def test_decision_key_on_unchanged_question_is_unknown_decision(client):
    scenario = build_scenario(client, "mig15e")
    fip_id = scenario["fip_id"]
    before = _updated_at(client, fip_id)

    r = client.post(
        f"/api/fips/{fip_id}/migrate",
        json={"to": "1.1.0", "decisions": {"splitCopies": {"F1-metadata": ["x"]}}},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown_decision"
    assert _updated_at(client, fip_id) == before


def test_orphan_reassign_target_hidden_or_answered_is_invalid_decision(client):
    scenario = build_scenario(client, "mig15f")
    fip_id = scenario["fip_id"]
    before = _updated_at(client, fip_id)

    # F2-metadata is outside A2's options (different ferType:
    # metadata-schema vs. A2's identifier-service) -- not a valid
    # orphanReassign target.
    r = client.post(
        f"/api/fips/{fip_id}/migrate",
        json={"to": "1.1.0", "decisions": {"orphanReassign": {"A2": "F2-metadata"}}},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_decision"
    assert _updated_at(client, fip_id) == before
