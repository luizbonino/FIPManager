"""spec 13-fip-dashboard.md §3.6: `GET /api/dashboard/{view}.csv`. Each
CSV is built from **the same view function** JSON uses (called with an
unbounded/maximal `limit`, capped at `FIPM_DASHBOARD_CSV_MAX_ROWS`) -- so
JSON and CSV can never disagree on the numbers (AC-22) by construction,
rather than by keeping two query implementations in sync by hand. UTF-8
with a leading BOM and CRLF line endings, matching `fipm.exporters`'s
existing FIP/session CSV exports."""

from __future__ import annotations

import csv
import io
from typing import Any

from fipm.config import get_settings

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> Any:
    """Same formula-injection guard as `fipm.exporters._csv_safe`."""
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _write(header: list[str], rows: list[list[Any]], *, truncated: bool) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([_csv_safe(h) for h in header])
    for row in rows:
        writer.writerow([_csv_safe(v) for v in row])
    if truncated:
        writer.writerow(["# truncated"])
    return "﻿" + buf.getvalue()


def coverage_csv(data: dict[str, Any]) -> str:
    header = [
        "key",
        "level",
        "principle",
        "principleGroup",
        "questions",
        "ferTypes",
        "current",
        "planned",
        "none",
        "notApplicable",
        "unanswered",
        "absent",
    ]
    rows = []
    max_rows = get_settings().dashboard_csv_max_rows
    for r in data["rows"][:max_rows]:
        c = r["counts"]
        rows.append(
            [
                r["key"],
                r["level"],
                r["principle"] or "",
                r["principleGroup"],
                ";".join(r["questions"]),
                ";".join(r["ferTypes"]),
                c["current"],
                c["planned"],
                c["none"],
                c["notApplicable"],
                c["unanswered"],
                c["absent"],
            ]
        )
    return _write(header, rows, truncated=len(data["rows"]) > max_rows)


def adoption_csv(data: dict[str, Any]) -> str:
    header = ["ferKey", "ferId", "label", "ferType", "status", "fips", "declarations", "share"]
    max_rows = get_settings().dashboard_csv_max_rows
    rows = [
        [
            r["ferKey"],
            r["ferId"] or "",
            r["label"] or "",
            r["ferType"] or "",
            r["status"],
            r["fips"],
            r["declarations"],
            r["share"],
        ]
        for r in data["rows"][:max_rows]
    ]
    truncated = data.get("truncated", False) or len(data["rows"]) > max_rows
    return _write(header, rows, truncated=truncated)


def gaps_csv(data: dict[str, Any]) -> str:
    header = [
        "questionId",
        "questionIndex",
        "subPrinciple",
        "principleGroup",
        "ferType",
        "fips",
        "unanswered",
        "noneOnly",
        "notApplicable",
        "plannedOnly",
        "coherenceFlags",
        "typeMismatches",
        "share",
    ]
    max_rows = get_settings().dashboard_csv_max_rows
    rows = [
        [
            r["questionId"],
            r["questionIndex"],
            r["subPrinciple"] or "",
            r["principleGroup"],
            r["ferType"] or "",
            r["fips"],
            r["unanswered"],
            r["noneOnly"],
            r["notApplicable"],
            r["plannedOnly"],
            r["coherenceFlags"],
            r["typeMismatches"],
            r["share"],
        ]
        for r in data["rows"][:max_rows]
    ]
    return _write(header, rows, truncated=len(data["rows"]) > max_rows)


def evolution_csv(data: dict[str, Any]) -> str:
    header = ["kind", "subPrinciple", "questionId", "status", "ferKey", "successorFerKey", "fips"]
    max_rows = get_settings().dashboard_csv_max_rows
    rows = []
    for r in data["planned"]["rows"][:max_rows]:
        rows.append(
            [
                "planned",
                r["subPrinciple"] or "",
                r["questionId"],
                r["status"],
                r["ferKey"],
                r["successorFerKey"] or "",
                r["fips"],
            ]
        )
    for r in data["migrations"]["rows"][: max(max_rows - len(rows), 0)]:
        rows.append(
            [
                "migration",
                "",
                f"{r['questionnaireId']}@{r['questionnaireVersion']}",
                "",
                f"{r['migratedFromId']}@{r['migratedFromVersion']}",
                "",
                r["fips"],
            ]
        )
    truncated = (
        data["planned"].get("truncated", False)
        or data["migrations"].get("truncated", False)
        or len(rows) >= max_rows
    )
    return _write(header, rows, truncated=truncated)


# ---------------------------------------------------------------------------
# Brief B, spec §4/§3.3: similarity CSV siblings.
# ---------------------------------------------------------------------------


def pair_csv(data: dict[str, Any]) -> str:
    header = ["questionId", "jaccard", "included"]
    rows = [[q["questionId"], q["jaccard"], q["included"]] for q in data["perQuestion"]]
    rows.append(["# overall", data["overall"], data["weighting"]])
    return _write(header, rows, truncated=False)


def neighbours_csv(data: dict[str, Any]) -> str:
    max_rows = get_settings().dashboard_csv_max_rows
    header = ["fipId", "label", "areaKey", "similarity", "sharedKeys"]
    rows = [
        [n["fipId"], n["label"], n["areaKey"] or "", n["similarity"], n["sharedKeys"]]
        for n in data["neighbours"][:max_rows]
    ]
    return _write(header, rows, truncated=len(data["neighbours"]) > max_rows)


def clusters_csv(data: dict[str, Any]) -> str:
    max_rows = get_settings().dashboard_csv_max_rows
    header = [
        "id",
        "size",
        "representativeFipId",
        "representativeLabel",
        "meanSimilarity",
        "principles",
    ]
    rows = [
        [
            c["id"],
            c["size"],
            c["representative"]["fipId"],
            c["representative"]["label"],
            c["meanSimilarity"],
            ";".join(c["principles"]),
        ]
        for c in data["clusters"][:max_rows]
    ]
    return _write(
        header, rows, truncated=data.get("truncated", False) or len(data["clusters"]) > max_rows
    )


def map_csv(data: dict[str, Any]) -> str:
    header = ["bucket", "from", "to", "count"]
    rows = [[h["bucket"], h["from"], h["to"], h["count"]] for h in data["histogram"]]
    return _write(header, rows, truncated=False)
