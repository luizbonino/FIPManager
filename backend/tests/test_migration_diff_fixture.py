"""AC20's backend half (the vitest half lives in
frontend/src/lib/migration.test.ts): `fipm.migration.compute_diff` against
the shared fixture pair under `tests/fixtures/migration/` -- the same
old/new model content and expected diff the frontend's `lib/migration.ts`
is meant to be checked against, so both implementations can't silently
drift. Also covers `apply_migration`'s default and custom-decision paths and
its two error codes directly (no HTTP layer), since those pure functions
have no other unit-level coverage."""

from __future__ import annotations

import json
from pathlib import Path

from fipm.migration import MigrationError, apply_migration, compute_diff, parse_semver, semver_gt

FIXTURES = Path(__file__).parent / "fixtures" / "migration"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_compute_diff_matches_fixture_pair():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    expected = _load("expected-diff.json")

    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )
    diff.pop("generatedAt")
    assert diff == expected


def test_compute_diff_never_mutates_inputs():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    old_copy, new_copy, answers_copy = (
        json.loads(json.dumps(old)),
        json.loads(json.dumps(new)),
        json.loads(json.dumps(answers)),
    )

    compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )
    assert old == old_copy
    assert new == new_copy
    assert answers == answers_copy


def test_identical_documents_yield_all_unchanged():
    old = _load("old-model.json")
    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": old["id"], "version": old["version"], "changelog": []},
        old,
        old,
        [],
    )
    assert all(item["status"] == "unchanged" for item in diff["items"])
    assert diff["counts"]["unchanged"] == 4
    assert diff["counts"]["added"] == 0
    assert diff["counts"]["removed"] == 0
    assert diff["counts"]["split"] == 0


def test_apply_migration_defaults():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )

    new_answers, orphaned = apply_migration(diff, answers, None, "1.0.0")
    by_id = {a["questionId"]: a for a in new_answers}
    assert by_id.keys() == {"F1-metadata", "F3", "F2-metadata", "F2-data"}
    assert len(orphaned) == 1
    assert orphaned[0]["questionId"] == "A2"
    assert orphaned[0]["fromVersion"] == "1.0.0"
    assert orphaned[0]["declarations"][0]["ferId"] == "https://w3id.org/np/orcid"


def test_apply_migration_custom_decisions():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )

    new_answers, orphaned = apply_migration(
        diff,
        answers,
        {"splitCopies": {"F2": ["F2-metadata"]}, "orphanReassign": {"A2": "R1.3-data"}},
        "1.0.0",
    )
    by_id = {a["questionId"]: a for a in new_answers}
    assert "F2-metadata" in by_id
    assert "F2-data" not in by_id
    assert "R1.3-data" in by_id
    # AC14: orphanReassign still records the orphanedAnswers entry.
    assert len(orphaned) == 1
    assert orphaned[0]["questionId"] == "A2"


def test_apply_migration_empty_split_list_orphans():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )

    new_answers, orphaned = apply_migration(diff, answers, {"splitCopies": {"F2": []}}, "1.0.0")
    by_id = {a["questionId"]: a for a in new_answers}
    assert "F2-metadata" not in by_id
    assert "F2-data" not in by_id
    orphaned_ids = {o["questionId"] for o in orphaned}
    assert "F2" in orphaned_ids
    assert "A2" in orphaned_ids


def test_apply_migration_unknown_decision():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )
    try:
        apply_migration(diff, answers, {"splitCopies": {"F1-metadata": ["x"]}}, "1.0.0")
        raise AssertionError("expected MigrationError")
    except MigrationError as exc:
        assert exc.code == "unknown_decision"


def test_apply_migration_invalid_decision():
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = _load("answers.json")
    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )
    try:
        apply_migration(diff, answers, {"orphanReassign": {"A2": "F2-metadata"}}, "1.0.0")
        raise AssertionError("expected MigrationError")
    except MigrationError as exc:
        assert exc.code == "invalid_decision"


def test_compute_diff_surfaces_answer_to_id_absent_from_both_models():
    """Audit finding 2: `compute_diff`'s pass 2 used to iterate only the
    source model's questions, so an answer whose questionId is in neither
    the source nor the target model (e.g. left over from an earlier bug,
    or hand-edited data) raised no diff item at all -- `apply_migration`
    then silently dropped it instead of keeping or orphaning it."""
    old = _load("old-model.json")
    new = _load("new-model.json")
    answers = [
        *_load("answers.json"),
        {"questionId": "ghost-question", "declarations": [], "comment": "still here"},
    ]

    diff = compute_diff(
        {"id": old["id"], "version": old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        old,
        new,
        answers,
    )
    ghost_items = [i for i in diff["items"] if i["oldQuestionId"] == "ghost-question"]
    assert len(ghost_items) == 1
    item = ghost_items[0]
    assert item["status"] == "removed"
    assert item["answered"] is True
    assert item["oldText"] == ""

    new_answers, orphaned = apply_migration(diff, answers, None, "1.0.0")
    assert "ghost-question" not in {a["questionId"] for a in new_answers}
    assert "ghost-question" in {o["questionId"] for o in orphaned}


def test_compute_diff_missing_source_content_still_surfaces_leftover_answers():
    """Audit finding 2: when `from_content` itself is missing/empty (e.g.
    the source knowledge-model version's content couldn't be loaded), pass
    2 used to iterate zero source questions, so every answer whose id is
    also absent from the target vanished with no diff item -- and
    `apply_migration` would then wipe those answers entirely instead of
    orphaning them. (F2 and A2 -- unlike F1-metadata/F3 -- aren't in the
    target model either, so they exercise pass 2, not the unrelated pass-1
    "added" path for ids the empty source can't resolve.)"""
    new = _load("new-model.json")
    answers = _load("answers.json")
    empty_old = {"id": "gone", "version": "0.0.0", "sections": []}

    diff = compute_diff(
        {"id": empty_old["id"], "version": empty_old["version"]},
        {"id": new["id"], "version": new["version"], "changelog": new["changelog"]},
        empty_old,
        new,
        answers,
    )
    removed_ids = {i["oldQuestionId"] for i in diff["items"] if i["status"] == "removed"}
    assert {"F2", "A2"} <= removed_ids

    new_answers, orphaned = apply_migration(diff, answers, None, "0.0.0")
    orphaned_ids = {o["questionId"] for o in orphaned}
    assert {"F2", "A2"} <= orphaned_ids


def test_apply_migration_rejects_duplicate_target_across_removed_items():
    """Audit finding 5: two different removed old ids reassigned (via
    `orphanReassign`) to the same target id used to produce two answers on
    that one question id. The second claim on an already-claimed target is
    now `invalid_decision`."""
    diff = {
        "items": [
            {
                "status": "removed",
                "oldQuestionId": "old-a",
                "newQuestionId": None,
                "decision": {"kind": "orphanReassign", "options": ["target-x"], "default": None},
            },
            {
                "status": "removed",
                "oldQuestionId": "old-b",
                "newQuestionId": None,
                "decision": {"kind": "orphanReassign", "options": ["target-x"], "default": None},
            },
        ]
    }
    answers = [
        {"questionId": "old-a", "declarations": [{"ferFreeText": "x", "status": "current"}]},
        {"questionId": "old-b", "declarations": [{"ferFreeText": "y", "status": "current"}]},
    ]
    decisions = {"orphanReassign": {"old-a": "target-x", "old-b": "target-x"}}
    try:
        apply_migration(diff, answers, decisions, "1.0.0")
        raise AssertionError("expected MigrationError")
    except MigrationError as exc:
        assert exc.code == "invalid_decision"


def test_apply_migration_dedupes_split_copies_list():
    """Audit finding 5: a caller-supplied `splitCopies` list naming the
    same target twice must produce one answer on that id, not two."""
    diff = {
        "items": [
            {
                "status": "split",
                "oldQuestionId": "old-a",
                "newQuestionId": None,
                "splitInto": ["target-1", "target-2"],
                "decision": {
                    "kind": "splitCopies",
                    "options": ["target-1", "target-2"],
                    "default": ["target-1", "target-2"],
                },
            }
        ]
    }
    answers = [{"questionId": "old-a", "declarations": [{"ferFreeText": "x", "status": "current"}]}]
    decisions = {"splitCopies": {"old-a": ["target-1", "target-1"]}}
    new_answers, orphaned = apply_migration(diff, answers, decisions, "1.0.0")
    assert [a["questionId"] for a in new_answers] == ["target-1"]
    assert orphaned == []


def test_semver_helpers():
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert semver_gt("1.1.0", "1.0.0")
    assert not semver_gt("1.0.0", "1.0.0")
    assert not semver_gt("0.9.0", "1.0.0")
