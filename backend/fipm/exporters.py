"""FIP -> export JSON (§3.1) and FIP -> CSV (§3.2)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fipm.config import Settings
from fipm.dmp import resolve_dmp_evidence_for_export
from fipm.models import Fer, Fip, KnowledgeModel, WorkshopSession

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
            if stored:
                comment = stored.get("comment")
                for decl in stored.get("declarations", []):
                    fer_obj = None
                    fer_id = decl.get("ferId")
                    if fer_id:
                        fer_row = db.get(Fer, fer_id)
                        if fer_row:
                            fer_obj = {
                                "id": fer_row.id,
                                "label": resolve_lang(fer_row.label, language, default_language),
                                "type": fer_row.type,
                                "homepage": fer_row.homepage,
                            }
                        else:
                            fer_obj = {"id": fer_id, "label": None, "type": None, "homepage": None}
                    declarations.append(
                        {
                            "fer": fer_obj,
                            "ferFreeText": decl.get("ferFreeText"),
                            "status": decl.get("status"),
                            "note": resolve_lang(decl.get("note"), language, default_language),
                            "dmpEvidence": resolve_dmp_evidence_for_export(
                                decl.get("dmpEvidence"), related_dmps
                            ),
                        }
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
                }
            )

    return {
        "exportVersion": 1,
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
        },
        "questionnaireRef": {
            "id": fip.questionnaire_id,
            "version": fip.questionnaire_version,
            "title": resolve_lang(content.get("title"), language, default_language),
            "source": content.get("source"),
        },
        "answers": out_answers,
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
        if not declarations:
            rows.append(base + ["", "", "", "", "", "", answer["comment"] or "", "", "", ""])
        else:
            for idx, decl in enumerate(declarations):
                fer = decl.get("fer") or {}
                dmp_evidence = decl.get("dmpEvidence") or {}
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
SESSION_CSV_HEADER = ["session_id", "fip_title", *CSV_HEADER]


def build_session_export_json(
    db: Session,
    session: WorkshopSession,
    fips: list[Fip],
    settings: Settings,
    facilitator_name: str,
) -> dict[str, Any]:
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
            "facilitatorName": facilitator_name,
            "createdAt": _iso_utc(session.created_at),
        },
        "fips": [build_export_json(db, fip, settings) for fip in fips],
    }


def build_session_export_csv(
    db: Session, session: WorkshopSession, fips: list[Fip], settings: Settings
) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    _write_csv_row(writer, SESSION_CSV_HEADER)
    for fip in fips:
        doc = build_export_json(db, fip, settings)
        fip_title = (fip.community or {}).get("name") if fip.community else None
        for row in _fip_csv_rows(fip, doc):
            _write_csv_row(writer, [session.id, fip_title or "", *row])
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


def reconstruct_answers_from_export(
    export_answers: list[dict[str, Any]],
    language: str,
    related_dmps: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Inverse of build_export_json's answer enrichment, for POST /fips/import."""
    url_to_index = {d["url"]: i for i, d in enumerate(related_dmps or [])}
    answers: list[dict[str, Any]] = []
    for answer in export_answers:
        declarations = []
        for decl in answer.get("declarations", []):
            fer_obj = decl.get("fer")
            fer_id = fer_obj.get("id") if fer_obj else None
            note_text = decl.get("note")
            declarations.append(
                {
                    "ferId": fer_id,
                    "ferFreeText": decl.get("ferFreeText"),
                    "status": decl.get("status"),
                    "note": {language: note_text} if note_text else None,
                    "dmpEvidence": _reconstruct_dmp_evidence(decl.get("dmpEvidence"), url_to_index),
                }
            )
        answers.append(
            {
                "questionId": answer["questionId"],
                "declarations": declarations,
                "comment": answer.get("comment"),
            }
        )
    return answers
