"""FIP migration between knowledge-model versions -- pure diff/apply
functions (spec 07-mail-and-migration.md §4.1/§4.2/§4.3), mirrored in
`frontend/src/lib/migration.ts` so both implementations can be checked
against the same fixtures (`tests/fixtures/migration/`, AC20). Nothing here
performs I/O or touches the DB -- `fipm.routers.fips` supplies the two
`content` documents and the FIP's `answers`/`questionnaire_version` and
persists the result.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

# Canonical semver: digits only per part, no leading zero unless the part is
# exactly "0" -- same rule as knowledge_models._is_canonical_semver_part.
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class InvalidSemver(ValueError):
    pass


class MigrationError(Exception):
    """Raised by `apply_migration` with a spec §4.3 error code
    (`unknown_decision` | `invalid_decision`); the router maps it to 400."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def parse_semver(version: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.match(version)
    if not match:
        raise InvalidSemver(version)
    a, b, c = match.groups()
    return int(a), int(b), int(c)


def semver_key(version: str) -> tuple[int, int, int]:
    """Like `parse_semver`, but never raises -- a malformed version sorts
    first (least), for read-path sorting that must not 500."""
    try:
        return parse_semver(version)
    except InvalidSemver:
        return (-1, -1, -1)


def semver_gt(a: str, b: str) -> bool:
    return parse_semver(a) > parse_semver(b)


# ---------------------------------------------------------------------------
# §4.1 diff algorithm
# ---------------------------------------------------------------------------


def _flatten(content: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in content.get("sections") or []:
        for q in section.get("questions") or []:
            out.append(
                {
                    "id": q["id"],
                    "text": q.get("text") or {},
                    "ferType": q.get("ferType"),
                    "hidden": bool(q.get("hidden")),
                }
            )
    return out


def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _en_text(q: dict[str, Any]) -> str:
    return q["text"].get("en") or ""


def _build_answered_index(answers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """spec §4.1: "a question id carrying at least one declaration or a
    non-empty comment counts as answered"."""
    index: dict[str, dict[str, Any]] = {}
    for answer in answers or []:
        has_declarations = bool(answer.get("declarations"))
        comment = answer.get("comment")
        has_comment = bool(comment and str(comment).strip())
        if has_declarations or has_comment:
            index[answer["questionId"]] = answer
    return index


def _empty_counts() -> dict[str, int]:
    return {
        "unchanged": 0,
        "added": 0,
        "removed": 0,
        "hidden": 0,
        "split": 0,
        "textChanged": 0,
        "ferTypeChanged": 0,
        "answersKept": 0,
        "answersOrphaned": 0,
        "decisionsRequired": 0,
    }


def _compute_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = _empty_counts()
    for item in items:
        counts[item["status"]] += 1
        flags = item.get("flags") or []
        if "text-changed" in flags:
            counts["textChanged"] += 1
        if "fer-type-changed" in flags:
            counts["ferTypeChanged"] += 1
        if item.get("decision") is not None:
            counts["decisionsRequired"] += 1
        if item["status"] == "removed":
            counts["answersOrphaned"] += 1
        elif item.get("answered") and item["status"] in ("unchanged", "hidden", "split"):
            # Defaults keep the answer: unchanged/hidden verbatim, split
            # copied to both targets (spec §4.1's default effect).
            counts["answersKept"] += 1
    return counts


def compute_diff(
    from_ref: dict[str, str],
    to_ref: dict[str, Any],
    from_content: dict[str, Any],
    to_content: dict[str, Any],
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """The §4.2 diff document. `from_ref`/`to_ref` are `{"id","version"}`
    (`to_ref` additionally carries `changelog`, a list of changelog
    entries -- see `fipm.routers.fips` for how it's built). Iterates the
    target in section/question order, then the source's leftovers, exactly
    mirroring `frontend/src/lib/migration.ts::computeMigrationDiff`."""
    old_qs = _flatten(from_content)
    new_qs = _flatten(to_content)
    old_by_id = {q["id"]: q for q in old_qs}
    new_by_id = {q["id"]: q for q in new_qs}
    answered_by_id = _build_answered_index(answers)

    def decl_count(qid: str) -> int:
        a = answered_by_id.get(qid)
        return len(a.get("declarations") or []) if a else 0

    # split: an old id absent from the target while both `<id>-metadata` and
    # `<id>-data` are present in the target and absent from the source.
    split_targets_by_old_id: dict[str, tuple[str, str]] = {}
    consumed_new_ids: set[str] = set()
    for oq in old_qs:
        if oq["id"] in new_by_id:
            continue
        meta_id = f"{oq['id']}-metadata"
        data_id = f"{oq['id']}-data"
        if (
            meta_id in new_by_id
            and data_id in new_by_id
            and meta_id not in old_by_id
            and data_id not in old_by_id
        ):
            split_targets_by_old_id[oq["id"]] = (meta_id, data_id)
            consumed_new_ids.add(meta_id)
            consumed_new_ids.add(data_id)

    items: list[dict[str, Any]] = []

    # Pass 1: target order.
    for nq in new_qs:
        if nq["id"] in consumed_new_ids:
            continue
        oq = old_by_id.get(nq["id"])
        if oq is not None:
            flags: list[str] = []
            old_text = _en_text(oq)
            new_text = _en_text(nq)
            if _normalize_whitespace(old_text) != _normalize_whitespace(new_text):
                flags.append("text-changed")
            if oq["ferType"] != nq["ferType"]:
                flags.append("fer-type-changed")
            status = "hidden" if nq["hidden"] else "unchanged"
            items.append(
                {
                    "status": status,
                    "oldQuestionId": oq["id"],
                    "newQuestionId": nq["id"],
                    "oldText": old_text,
                    "newText": new_text,
                    "oldFerType": oq["ferType"],
                    "newFerType": nq["ferType"],
                    "flags": flags,
                    "answered": nq["id"] in answered_by_id,
                    "declarationCount": decl_count(nq["id"]),
                    "decision": None,
                }
            )
        else:
            items.append(
                {
                    "status": "added",
                    "oldQuestionId": None,
                    "newQuestionId": nq["id"],
                    "newText": _en_text(nq),
                    "newFerType": nq["ferType"],
                    "flags": [],
                    "answered": False,
                    "declarationCount": 0,
                    "decision": None,
                }
            )

    # Pass 2: source leftovers -- ids gone from the target -- plus (audit
    # finding 2) any answered question id that's absent from *both* models.
    # Driving this off `old_qs` alone loses those: an answer can reference
    # an id the source content no longer carries either (e.g. a prior
    # migration's `from_content` didn't include it, or `from_content` is
    # missing/empty entirely), and `apply_migration` only keeps or orphans
    # answers whose id has a diff item -- so an id skipped here doesn't
    # merely miss review, it silently vanishes on apply. Iterate the ids
    # `old_qs` supplies (in that order, unchanged) for source/ferType/text,
    # then any leftover answered id `old_qs` doesn't cover.
    old_leftover_ids = [oq["id"] for oq in old_qs if oq["id"] not in new_by_id]
    extra_answered_ids = [
        qid for qid in answered_by_id if qid not in new_by_id and qid not in old_by_id
    ]
    for old_id in old_leftover_ids + extra_answered_ids:
        oq = old_by_id.get(old_id)
        answered = old_id in answered_by_id
        split_into = split_targets_by_old_id.get(old_id)
        if split_into is not None:
            items.append(
                {
                    "status": "split",
                    "oldQuestionId": old_id,
                    "newQuestionId": None,
                    "oldText": _en_text(oq) if oq is not None else "",
                    "flags": [],
                    "answered": answered,
                    "declarationCount": decl_count(old_id),
                    "splitInto": list(split_into),
                    "decision": (
                        {
                            "kind": "splitCopies",
                            "options": list(split_into),
                            "default": list(split_into),
                        }
                        if answered
                        else None
                    ),
                }
            )
            continue
        if not answered:
            continue  # an unanswered, non-split leftover raises no item to review.
        removed_fer_type = oq["ferType"] if oq is not None else None
        unanswered_non_hidden = [
            q for q in new_qs if not q["hidden"] and q["id"] not in answered_by_id
        ]
        if removed_fer_type:
            options = [q["id"] for q in unanswered_non_hidden if q["ferType"] == removed_fer_type]
        else:
            options = [q["id"] for q in unanswered_non_hidden]
        if not options and removed_fer_type:
            options = [q["id"] for q in unanswered_non_hidden]
        items.append(
            {
                "status": "removed",
                "oldQuestionId": old_id,
                "newQuestionId": None,
                "oldText": _en_text(oq) if oq is not None else "",
                "flags": [],
                "answered": True,
                "declarationCount": decl_count(old_id),
                "decision": {"kind": "orphanReassign", "options": options, "default": None},
            }
        )

    return {
        "diffVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "from": {"id": from_ref["id"], "version": from_ref["version"]},
        "to": {
            "id": to_ref["id"],
            "version": to_ref["version"],
            "changelog": to_ref.get("changelog") or [],
        },
        "counts": _compute_counts(items),
        "items": items,
    }


def changelog_between(
    changelog: list[dict[str, Any]], from_version: str, to_version: str
) -> list[dict[str, Any]]:
    """Changelog entries strictly newer than `from_version` and up to and
    including `to_version`, ascending -- so an adjacent hop (1.0.0 -> 1.1.0)
    yields exactly the target's own entry, matching spec §4.2's example."""
    try:
        lo = parse_semver(from_version)
        hi = parse_semver(to_version)
    except InvalidSemver:
        return list(changelog)
    entries = []
    for entry in changelog or []:
        try:
            v = parse_semver(entry.get("version", ""))
        except InvalidSemver:
            continue
        if lo < v <= hi:
            entries.append(entry)
    entries.sort(key=lambda e: parse_semver(e["version"]))
    return entries


# ---------------------------------------------------------------------------
# §4.3/§4.4: apply a migration
# ---------------------------------------------------------------------------


def _orphan_entry(
    question_id: str,
    question_text_en: str | None,
    answer: dict[str, Any],
    from_version: str,
    at_iso: str,
) -> dict[str, Any]:
    return {
        "questionId": question_id,
        "questionText": {"en": question_text_en} if question_text_en else {},
        "declarations": answer.get("declarations") or [],
        "comment": answer.get("comment"),
        "fromVersion": from_version,
        "at": at_iso,
    }


def apply_migration(
    diff: dict[str, Any],
    answers: list[dict[str, Any]],
    decisions: dict[str, Any] | None,
    from_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate `decisions` against `diff` (already recomputed server-side by
    the caller) and return `(new_answers, orphaned_answers_to_append)`.
    `new_answers` is in target order (unchanged/hidden verbatim, split
    copied per decision, removed/absent split dropped); missing decisions
    take the §4.2 defaults. Raises `MigrationError("unknown_decision")` for
    a key that isn't a decidable item (or is decidable but of the other
    kind), and `MigrationError("invalid_decision")` for a `splitCopies`
    target outside that item's `splitInto`, or an `orphanReassign` target
    outside that item's `options` (spec §4.3: hidden, absent or already
    answered in the target)."""
    decisions = decisions or {}
    split_copies_input: dict[str, list[str]] = decisions.get("splitCopies") or {}
    orphan_reassign_input: dict[str, str] = decisions.get("orphanReassign") or {}

    decidable_by_old_id: dict[str, dict[str, Any]] = {
        item["oldQuestionId"]: item
        for item in diff["items"]
        if item.get("decision") is not None and item.get("oldQuestionId")
    }

    for key in split_copies_input:
        item = decidable_by_old_id.get(key)
        if item is None or item["decision"]["kind"] != "splitCopies":
            raise MigrationError("unknown_decision")
    for key in orphan_reassign_input:
        item = decidable_by_old_id.get(key)
        if item is None or item["decision"]["kind"] != "orphanReassign":
            raise MigrationError("unknown_decision")

    answers_by_id = {a["questionId"]: a for a in answers or []}
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    new_answers: list[dict[str, Any]] = []
    orphaned: list[dict[str, Any]] = []

    # Audit finding 5: `unchanged`/`hidden` targets are each some single
    # `nq["id"]` from pass 1 and so can't collide with one another, but a
    # `splitCopies`/`orphanReassign` target is caller-chosen and nothing
    # upstream stops two decisions (or a decision and a duplicate entry in
    # one `splitCopies` list) from naming the same target id -- which would
    # otherwise put two answers on one question. Track every id a decision
    # claims and reject a second claim as `invalid_decision`.
    claimed_target_ids: set[str] = set()

    def _claim(target_id: str) -> None:
        if target_id in claimed_target_ids:
            raise MigrationError("invalid_decision")
        claimed_target_ids.add(target_id)

    for item in diff["items"]:
        status = item["status"]
        if status in ("unchanged", "hidden"):
            old_id = item["oldQuestionId"]
            original = answers_by_id.get(old_id)
            if original is not None:
                _claim(item["newQuestionId"])
                a = dict(original)
                a["questionId"] = item["newQuestionId"]
                new_answers.append(a)
        elif status == "added":
            continue
        elif status == "split":
            old_id = item["oldQuestionId"]
            original = answers_by_id.get(old_id)
            if original is None:
                continue
            decision = item["decision"]
            chosen = split_copies_input.get(old_id, decision["default"])
            for target in chosen:
                if target not in item["splitInto"]:
                    raise MigrationError("invalid_decision")
            # dedupe the caller-supplied list itself before claiming.
            deduped_chosen = list(dict.fromkeys(chosen))
            if deduped_chosen:
                for target in deduped_chosen:
                    _claim(target)
                    a = dict(original)
                    a["questionId"] = target
                    new_answers.append(a)
            else:
                orphaned.append(
                    _orphan_entry(old_id, item.get("oldText"), original, from_version, now_iso)
                )
        elif status == "removed":
            old_id = item["oldQuestionId"]
            original = answers_by_id.get(old_id)
            if original is None:
                continue
            decision = item["decision"]
            target = orphan_reassign_input.get(old_id, decision["default"])
            if target is not None:
                if target not in decision["options"]:
                    raise MigrationError("invalid_decision")
                _claim(target)
                a = dict(original)
                a["questionId"] = target
                new_answers.append(a)
            # spec §4.2 AC14: an orphanReassign target still records the
            # orphanedAnswers entry -- append() happens whether or not
            # `target` was set.
            orphaned.append(
                _orphan_entry(old_id, item.get("oldText"), original, from_version, now_iso)
            )
        # "added" already handled; nothing else creates or drops answers.

    return new_answers, orphaned
