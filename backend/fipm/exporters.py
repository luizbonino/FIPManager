"""FIP -> export JSON (§3.1) and FIP -> CSV (§3.2)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fipm.authz import can_read
from fipm.config import Settings
from fipm.dmp import resolve_dmp_evidence_for_export
from fipm.models import Fer, Fip, KnowledgeModel, WorkshopSession
from fipm.schemas import session_questionnaire_refs

CSV_HEADER = [
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
    # spec 06-dmp-linkage.md §2.4: appended, so every existing column index
    # is unchanged.
    "dmp_url",
    "dmp_section",
    "dmp_question",
    # spec 05-v1-completion.md §5 (per the 9 Sep 2026 reconciliation note,
    # appended after the DMP columns spec 06 already added): 26 columns
    # total, the first 24 unchanged.
    "successor_fer_id",
    "successor_fer_label",
]


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> Any:
    """Guard against CSV/spreadsheet formula injection: prefix any cell whose
    first character is one of `=+-@\t\r` with a single quote, so spreadsheet
    apps that open the export render it as text instead of evaluating it as
    a formula. Applied to every header and data cell written to a CSV export."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _write_csv_row(writer: Any, row: list[Any]) -> None:
    writer.writerow([_csv_safe(cell) for cell in row])


def resolve_lang(
    langmap: dict[str, str] | None, language: str, default_language: str = "en"
) -> str | None:
    """pt-PT <-> pt-BR -> en fallback; else the first available value."""
    if not langmap:
        return None
    if language in langmap:
        return langmap[language]
    if language == "pt-PT" and "pt-BR" in langmap:
        return langmap["pt-BR"]
    if language == "pt-BR" and "pt-PT" in langmap:
        return langmap["pt-PT"]
    if default_language in langmap:
        return langmap[default_language]
    for value in langmap.values():
        return value
    return None


def fip_url(fip: Fip, settings: Settings) -> str:
    return f"{settings.base_url}/fips/{fip.id}"


def _iso_utc(value: datetime) -> str:
    """isoformat() ending in "Z": attach UTC to naive datetimes first (SQLite
    round-trips DateTime(timezone=True) values as naive)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def _enrich_fer_ref(
    db: Session, fer_id: str | None, language: str, default_language: str
) -> dict[str, Any] | None:
    """The `{id, label, type, homepage}` shape both `fer` and `successor`
    use, resolved off the `Fer` table row when it still exists (spec
    05-v1-completion.md §5)."""
    if not fer_id:
        return None
    fer_row = db.get(Fer, fer_id)
    if fer_row:
        return {
            "id": fer_row.id,
            "label": resolve_lang(fer_row.label, language, default_language),
            "type": fer_row.type,
            "homepage": fer_row.homepage,
        }
    return {"id": fer_id, "label": None, "type": None, "homepage": None}


def _enrich_declarations(
    db: Session,
    declarations: list[dict[str, Any]],
    language: str,
    default_language: str,
    related_dmps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Shared by the per-question `answers` loop and `orphanedAnswers`
    (spec 07-mail-and-migration.md §6): both export declarations the same
    way -- `fer`/`successor` resolved off the `Fer` table, `dmpEvidence`
    resolved against the FIP's `relatedDMPs`."""
    out: list[dict[str, Any]] = []
    for decl in declarations or []:
        out.append(
            {
                "fer": _enrich_fer_ref(db, decl.get("ferId"), language, default_language),
                "ferFreeText": decl.get("ferFreeText"),
                "status": decl.get("status"),
                "note": resolve_lang(decl.get("note"), language, default_language),
                "dmpEvidence": resolve_dmp_evidence_for_export(
                    decl.get("dmpEvidence"), related_dmps
                ),
                "successor": _enrich_fer_ref(
                    db, decl.get("successorFerId"), language, default_language
                ),
                "successorFreeText": decl.get("successorFreeText"),
            }
        )
    return out


def build_export_json(db: Session, fip: Fip, settings: Settings) -> dict[str, Any]:
    km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    content = km.content if km else {"sections": [], "title": {}, "source": None}
    language = fip.language
    default_language = settings.default_language

    answers_by_qid = {a["questionId"]: a for a in (fip.answers or [])}
    related_dmps = fip.related_dmps or []

    out_answers: list[dict[str, Any]] = []
    for section in content.get("sections", []):
        for question in section.get("questions", []):
            # spec 04-knowledge-model-editor.md §4: hidden questions are
            # skipped by exports (no padded row, no `answers` entry) even if
            # the FIP still stores an answer from before it was hidden.
            if question.get("hidden") is True:
                continue
            qid = question["id"]
            stored = answers_by_qid.get(qid)
            declarations: list[dict[str, Any]] = []
            comment = None
            not_applicable = False
            if stored:
                comment = stored.get("comment")
                not_applicable = bool(stored.get("notApplicable"))
                declarations = _enrich_declarations(
                    db, stored.get("declarations", []), language, default_language, related_dmps
                )
            out_answers.append(
                {
                    "sectionId": section["id"],
                    "sectionTitle": resolve_lang(section.get("title"), language, default_language),
                    "questionId": qid,
                    "questionText": resolve_lang(question.get("text"), language, default_language),
                    "principle": question.get("principle"),
                    "scope": question.get("scope"),
                    "ferType": question.get("ferType"),
                    "declarations": declarations,
                    "comment": comment,
                    # spec 08-workshop-picklists.md §2.3: always present (like
                    # `comment`), true only for a per-answer "not applicable"
                    # flag; mutually exclusive with `declarations` (schema
                    # validator).
                    "notApplicable": not_applicable,
                }
            )

    # spec 07-mail-and-migration.md §6: exportVersion 2 -- `fip.migratedFrom`
    # and a top-level `orphanedAnswers` array, FER-enriched like `answers`.
    # Readers of exportVersion 1 are unaffected: both fields are additive.
    out_orphaned: list[dict[str, Any]] = []
    for entry in fip.orphaned_answers or []:
        out_orphaned.append(
            {
                "questionId": entry.get("questionId"),
                "questionText": entry.get("questionText") or {},
                "declarations": _enrich_declarations(
                    db, entry.get("declarations", []), language, default_language, related_dmps
                ),
                "comment": entry.get("comment"),
                "notApplicable": bool(entry.get("notApplicable")),
                "fromVersion": entry.get("fromVersion"),
                "at": entry.get("at"),
            }
        )

    return {
        "exportVersion": 2,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "tool": {"name": "FIP Manager", "baseUrl": settings.base_url},
        "fip": {
            "id": fip.id,
            "url": fip_url(fip, settings),
            "language": fip.language,
            "license": fip.license,
            "visibility": fip.visibility,
            "createdAt": _iso_utc(fip.created_at),
            "updatedAt": _iso_utc(fip.updated_at),
            "community": fip.community,
            "relatedDMPs": fip.related_dmps or [],
            "migratedFrom": fip.migrated_from,
            # spec 11-nanopub-network.md §4: null for every FIP not created
            # via POST /fips/from-network.
            "networkOrigin": fip.network_origin,
        },
        "questionnaireRef": {
            "id": fip.questionnaire_id,
            "version": fip.questionnaire_version,
            "title": resolve_lang(content.get("title"), language, default_language),
            "source": content.get("source"),
        },
        "answers": out_answers,
        "orphanedAnswers": out_orphaned,
    }


def _fip_csv_rows(fip: Fip, doc: dict[str, Any]) -> list[list[Any]]:
    """One CSV row (matching `CSV_HEADER`) per declaration of `doc`, plus one
    row for each unanswered question. Shared by the single-FIP export and the
    session-wide export (spec 02-core-flows.md §5.3), which prepends its own
    `session_id, fip_title` columns to each row."""
    rows: list[list[Any]] = []
    community_name = (fip.community or {}).get("name", "") if fip.community else ""

    for answer in doc["answers"]:
        base = [
            doc["fip"]["id"],
            doc["fip"]["url"],
            doc["fip"]["language"],
            doc["fip"]["license"],
            fip.questionnaire_id,
            fip.questionnaire_version,
            community_name or "",
            answer["sectionId"],
            answer["sectionTitle"] or "",
            answer["questionId"],
            answer["questionText"] or "",
            answer["principle"] or "",
            answer["scope"] or "",
            answer["ferType"] or "",
        ]
        declarations = answer["declarations"]
        if answer.get("notApplicable"):
            # spec 08-workshop-picklists.md §2.3: a single row, `status` =
            # "not-applicable" (a CSV rendering only -- never a stored
            # declaration status), the 10 declaration/dmp/successor columns
            # empty, `comment` as usual. Mutually exclusive with
            # `declarations` (schema validator), so this never runs
            # alongside the per-declaration branch below.
            rows.append(
                base
                + [
                    "",
                    "",
                    "",
                    "",
                    "not-applicable",
                    "",
                    answer["comment"] or "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
        elif not declarations:
            rows.append(
                base + ["", "", "", "", "", "", answer["comment"] or "", "", "", "", "", ""]
            )
        else:
            for idx, decl in enumerate(declarations):
                fer = decl.get("fer") or {}
                dmp_evidence = decl.get("dmpEvidence") or {}
                successor = decl.get("successor") or {}
                successor_label = successor.get("label") or decl.get("successorFreeText") or ""
                rows.append(
                    base
                    + [
                        idx,
                        fer.get("id") or "",
                        fer.get("label") or "",
                        decl.get("ferFreeText") or "",
                        decl.get("status") or "",
                        decl.get("note") or "",
                        answer["comment"] or "",
                        dmp_evidence.get("dmpUrl") or "",
                        dmp_evidence.get("section") or "",
                        dmp_evidence.get("questionRef") or "",
                        successor.get("id") or "",
                        successor_label,
                    ]
                )
    return rows


def build_export_csv(db: Session, fip: Fip, settings: Settings) -> str:
    doc = build_export_json(db, fip, settings)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    _write_csv_row(writer, CSV_HEADER)
    for row in _fip_csv_rows(fip, doc):
        _write_csv_row(writer, row)
    return "﻿" + buf.getvalue()


# spec 02-core-flows.md §5.3: session-wide export, columns prefixed by
# `session_id, fip_title` (= community.name), all FIPs under one header row.
# spec 08-workshop-picklists.md §3.3: an `area` column is prepended as the
# third prefix column for a multi-ref session; the single-FIP CSV
# (CSV_HEADER) is untouched.
SESSION_CSV_HEADER = ["session_id", "fip_title", "area", *CSV_HEADER]


def resolve_session_questionnaire_refs(
    db: Session, session: WorkshopSession
) -> list[dict[str, Any]]:
    """spec 08-workshop-picklists.md §3.1/§3.3/§5.8: the session's ref list,
    each resolved to `{id, version, label, title}` -- `title` is the
    referenced model's own title, filtered by the same anonymous-
    readability rule that guards `questionnaireTitle` today (published AND
    anonymously readable, else `{}`); `label` falls back to that title when
    the ref itself carries none (the NULL-column derived single-ref case).
    Shared by `routers.sessions` (`SessionOut`/`SessionPublicOut`) and the
    session export builders below."""
    refs = session_questionnaire_refs(session)
    out: list[dict[str, Any]] = []
    for ref in refs:
        km = db.get(KnowledgeModel, (ref["id"], ref["version"]))
        title: dict[str, Any] = {}
        if (
            km is not None
            and km.status == "published"
            and can_read(km.owner_id, km.visibility, None)
        ):
            title = km.title or {}
        label = ref.get("label") or title
        out.append(
            {"id": ref["id"], "version": ref["version"], "label": label or {}, "title": title}
        )
    return out


def _fip_area(refs: list[dict[str, Any]], fip: Fip) -> dict[str, Any] | None:
    """spec 08 §3.2/§3.3: non-null only for a FIP in a multi-ref session,
    looked up from the session's ref list (never copied onto the FIP row)."""
    if len(refs) <= 1:
        return None
    for ref in refs:
        if ref["id"] == fip.questionnaire_id and ref["version"] == fip.questionnaire_version:
            return {"id": ref["id"], "version": ref["version"], "label": ref["label"]}
    return None


def build_session_export_json(
    db: Session,
    session: WorkshopSession,
    fips: list[Fip],
    settings: Settings,
    facilitator_name: str,
) -> dict[str, Any]:
    refs = resolve_session_questionnaire_refs(db, session)
    fip_docs: list[dict[str, Any]] = []
    for fip in fips:
        doc = build_export_json(db, fip, settings)
        doc["area"] = _fip_area(refs, fip)
        fip_docs.append(doc)
    return {
        "exportVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "tool": {"name": "FIP Manager", "baseUrl": settings.base_url},
        "session": {
            "id": session.id,
            "title": session.title,
            "status": session.status,
            "joinCode": session.join_code,
            "defaultLanguage": session.default_language,
            "questionnaireRef": {
                "id": session.questionnaire_id,
                "version": session.questionnaire_version,
            },
            # spec 08 §3.3: the full ref list, first entry == questionnaireRef.
            "questionnaireRefs": [
                {"id": r["id"], "version": r["version"], "label": r["label"]} for r in refs
            ],
            "facilitatorName": facilitator_name,
            "createdAt": _iso_utc(session.created_at),
        },
        "fips": fip_docs,
    }


def build_session_export_csv(
    db: Session, session: WorkshopSession, fips: list[Fip], settings: Settings
) -> str:
    refs = resolve_session_questionnaire_refs(db, session)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    _write_csv_row(writer, SESSION_CSV_HEADER)
    for fip in fips:
        doc = build_export_json(db, fip, settings)
        fip_title = (fip.community or {}).get("name") if fip.community else None
        area = _fip_area(refs, fip)
        area_label = (
            resolve_lang(area["label"], fip.language, settings.default_language) if area else ""
        )
        for row in _fip_csv_rows(fip, doc):
            _write_csv_row(writer, [session.id, fip_title or "", area_label or "", *row])
    return "﻿" + buf.getvalue()


def _reconstruct_dmp_evidence(
    dmp_evidence: dict[str, Any] | None, url_to_index: dict[str, int]
) -> dict[str, Any] | None:
    """Inverse of `resolve_dmp_evidence_for_export`, for POST /fips/import
    (spec 06-dmp-linkage.md §2.4): match the export's `dmpUrl` against the
    *imported* document's (already-normalised) `relatedDMPs`, falling back
    to the export's own `dmpIndex` when the URL isn't found there. Covers
    the legacy `{url, questionRef}` stored shape too, since its export also
    carries `dmpUrl` (with `dmpIndex` null)."""
    if not dmp_evidence:
        return None
    url = dmp_evidence.get("dmpUrl")
    index = url_to_index.get(url) if url else None
    if index is None:
        index = dmp_evidence.get("dmpIndex")
    if not isinstance(index, int) or isinstance(index, bool):
        return None
    return {
        "dmpIndex": index,
        "section": dmp_evidence.get("section"),
        "questionRef": dmp_evidence.get("questionRef"),
    }


def _reconstruct_declarations(
    export_declarations: list[dict[str, Any]], language: str, url_to_index: dict[str, int]
) -> list[dict[str, Any]]:
    """Inverse of `_enrich_declarations`, shared by `reconstruct_answers_
    from_export` and `reconstruct_orphaned_answers_from_export` (spec
    07-mail-and-migration.md §6: "import must accept both versions" and
    preserve `orphanedAnswers` the same way it already preserves `answers`)."""
    declarations = []
    for decl in export_declarations or []:
        fer_obj = decl.get("fer")
        fer_id = fer_obj.get("id") if fer_obj else None
        successor_obj = decl.get("successor")
        successor_fer_id = successor_obj.get("id") if successor_obj else None
        note_text = decl.get("note")
        declarations.append(
            {
                "ferId": fer_id,
                "ferFreeText": decl.get("ferFreeText"),
                "status": decl.get("status"),
                "note": {language: note_text} if note_text else None,
                "dmpEvidence": _reconstruct_dmp_evidence(decl.get("dmpEvidence"), url_to_index),
                # spec 05-v1-completion.md §5: inverse of the "successor"
                # enrichment above, so POST /fips/import round-trips both
                # successor fields.
                "successorFerId": successor_fer_id,
                "successorFreeText": decl.get("successorFreeText"),
            }
        )
    return declarations


def reconstruct_answers_from_export(
    export_answers: list[dict[str, Any]],
    language: str,
    related_dmps: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Inverse of build_export_json's answer enrichment, for POST /fips/import."""
    url_to_index = {d["url"]: i for i, d in enumerate(related_dmps or [])}
    answers: list[dict[str, Any]] = []
    for answer in export_answers:
        entry: dict[str, Any] = {
            "questionId": answer["questionId"],
            "declarations": _reconstruct_declarations(
                answer.get("declarations", []), language, url_to_index
            ),
            "comment": answer.get("comment"),
        }
        # spec 08-workshop-picklists.md §2.3: POST /fips/import round-trips
        # `notApplicable`; the `Answer` schema (fipm.schemas) itself drops a
        # `false` value before it's stored, keeping old blobs unchanged, so
        # only pass it through when true.
        if answer.get("notApplicable"):
            entry["notApplicable"] = True
        answers.append(entry)
    return answers


def reconstruct_orphaned_answers_from_export(
    export_orphaned: list[dict[str, Any]],
    language: str,
    related_dmps: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Inverse of `build_export_json`'s `orphanedAnswers` enrichment (spec
    07-mail-and-migration.md §6): POST /fips/import preserves the §4.4
    shape verbatim (`questionId`, `questionText`, `fromVersion`, `at`),
    reconstructing only `declarations` the same way `answers` are."""
    url_to_index = {d["url"]: i for i, d in enumerate(related_dmps or [])}
    orphaned: list[dict[str, Any]] = []
    for entry in export_orphaned or []:
        orphaned.append(
            {
                "questionId": entry.get("questionId"),
                "questionText": entry.get("questionText") or {},
                "declarations": _reconstruct_declarations(
                    entry.get("declarations", []), language, url_to_index
                ),
                "comment": entry.get("comment"),
                "notApplicable": bool(entry.get("notApplicable")),
                "fromVersion": entry.get("fromVersion"),
                "at": entry.get("at"),
            }
        )
    return orphaned
