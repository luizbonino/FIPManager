"""FIP -> export JSON (§3.1) and FIP -> CSV (§3.2)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fipm.config import Settings
from fipm.models import Fer, Fip, KnowledgeModel

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
]


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

    out_answers: list[dict[str, Any]] = []
    for section in content.get("sections", []):
        for question in section.get("questions", []):
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
                            "dmpEvidence": decl.get("dmpEvidence"),
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


def build_export_csv(db: Session, fip: Fip, settings: Settings) -> str:
    doc = build_export_json(db, fip, settings)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
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
            writer.writerow(base + ["", "", "", "", "", "", answer["comment"] or ""])
        else:
            for idx, decl in enumerate(declarations):
                fer = decl.get("fer") or {}
                writer.writerow(
                    base
                    + [
                        idx,
                        fer.get("id") or "",
                        fer.get("label") or "",
                        decl.get("ferFreeText") or "",
                        decl.get("status") or "",
                        decl.get("note") or "",
                        answer["comment"] or "",
                    ]
                )
    return "﻿" + buf.getvalue()


def reconstruct_answers_from_export(
    export_answers: list[dict[str, Any]], language: str
) -> list[dict[str, Any]]:
    """Inverse of build_export_json's answer enrichment, for POST /fips/import."""
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
                    "dmpEvidence": decl.get("dmpEvidence"),
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
