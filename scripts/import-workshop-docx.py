#!/usr/bin/env python3
"""Import the CONFOA 2026 workshop picklist .docx into 11 area knowledge models.

See docs/specs/08-workshop-picklists.md §4. Stdlib only (zipfile, xml.etree,
json, re, argparse, pathlib, unicodedata, difflib, hashlib) -- no python-docx,
no new dependency.

    uv run --project backend python scripts/import-workshop-docx.py \\
        --docx "docs/workshop/PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx" \\
        [--base data/knowledge-models/gofair-fip-mini-1.0.0.json] \\
        [--seed data/fers/seed.json] \\
        [--map data/workshop/option-map.json] [--out data/knowledge-models] \\
        [--base-url https://fipm.example.org] [--report -] \\
        [--bump] [--strict] [--dry-run]

Every function below the CLI section is pure (no I/O), so
backend/tests/test_import_workshop_docx.py can exercise the parsing and
matching logic directly against a synthetic .docx built with `zipfile`,
without touching the real document or the filesystem layout under `data/`.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import io
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent

# --------------------------------------------------------------------------
# backend/fipm.km_content is the single source of truth for content
# validation and slugify (spec 04 §3.3); prefer importing it (that's what
# `uv run --project backend` guarantees is on sys.path) and fall back to a
# small re-implementation of the shape checks this script actually needs
# when backend/ isn't importable, per spec 4.3.
# --------------------------------------------------------------------------
try:
    sys.path.insert(0, str(_REPO_ROOT / "backend"))
    from fipm.km_content import validate_content as _real_validate_content

    _HAVE_FIPM = True
except Exception:  # pragma: no cover - exercised only when backend/ is absent
    _real_validate_content = None
    _HAVE_FIPM = False


_LANGUAGES = frozenset({"en", "pt-PT", "pt-BR", "es"})


def _fallback_validate_content(
    doc: dict[str, Any], *, publishing: bool = False
) -> list[dict[str, str]]:
    """A small subset of km_content.validate_content's shape checks, used
    only when backend/ is not importable (spec 4.3)."""
    errors: list[dict[str, str]] = []

    def err(path: str, code: str, message: str) -> None:
        errors.append({"path": path, "code": code, "message": message})

    def check_langmap(value: Any, path: str) -> None:
        if not isinstance(value, dict):
            err(path, "missing_key", f"{path} must be an object")
            return
        if "en" not in value:
            err(path, "missing_en", f"{path} must include an 'en' entry")
        for lang, text in value.items():
            if lang not in _LANGUAGES:
                err(f"{path}.{lang}", "unknown_language", f"unknown language {lang!r}")
            elif not isinstance(text, str) or text == "":
                err(f"{path}.{lang}", "empty_string", f"{path}.{lang} must be non-empty")

    check_langmap(doc.get("title"), "title")
    check_langmap(doc.get("description"), "description")
    sections = doc.get("sections")
    if not isinstance(sections, list):
        err("sections", "missing_key", "sections must be a list")
        sections = []
    question_ids: set[str] = set()
    for s_idx, section in enumerate(sections):
        if not isinstance(section, dict):
            err(f"sections[{s_idx}]", "missing_key", "section must be an object")
            continue
        for q_idx, question in enumerate(section.get("questions") or []):
            q_path = f"sections[{s_idx}].questions[{q_idx}]"
            if not isinstance(question, dict):
                err(q_path, "missing_key", "question must be an object")
                continue
            q_id = question.get("id")
            if not isinstance(q_id, str) or not q_id:
                err(f"{q_path}.id", "missing_key", "question id is required")
            elif q_id in question_ids:
                err(f"{q_path}.id", "duplicate_question_id", f"duplicate question id {q_id}")
            else:
                question_ids.add(q_id)
            check_langmap(question.get("text"), f"{q_path}.text")
    return errors


def validate_content(doc: dict[str, Any], *, known_fer_ids: set[str] | None = None) -> list[dict]:
    """Validate an emitted model document. Tries the real
    `km_content.validate_content` first (forward-compatible with spec 08 §1.2's
    not-yet-implemented `known_fer_ids` keyword: falls back to calling it
    without that keyword when it isn't accepted yet); falls back to the
    small local re-implementation when backend/ isn't importable at all."""
    if _real_validate_content is not None:
        try:
            return _real_validate_content(doc, known_fer_ids=known_fer_ids)
        except TypeError:
            return _real_validate_content(doc)
    return _fallback_validate_content(doc)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 48) -> str:
    """Identical rule to fipm.km_content.slugify, duplicated so this script
    has no hard runtime dependency on backend/ for such a small function."""
    slug = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return slug[:max_len].strip("-")


# --------------------------------------------------------------------------
# Text normalisation (spec 08 §4.1, §4.2)
# --------------------------------------------------------------------------


def strip_accents(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


_PAREN_RE = re.compile(r"\([^)]*\)")
_WS_RE = re.compile(r"\s+")
_TRAIL_PUNCT_RE = re.compile(r"[\s.,;:!?\-–—]+$")


def norm(s: str) -> str:
    """§4.2: NFC -> strip accents -> drop parenthesised text -> casefold ->
    collapse whitespace -> strip trailing punctuation."""
    text = unicodedata.normalize("NFC", s or "")
    text = strip_accents(text)
    text = _PAREN_RE.sub(" ", text)
    text = text.casefold()
    text = _WS_RE.sub(" ", text).strip()
    text = _TRAIL_PUNCT_RE.sub("", text)
    return text.strip()


_OTHER_SENTINELS = frozenset({"outro", "outros", "outra", "outras", "especificar", "other"})
_UNDEFINED_SENTINELS = frozenset({"ainda nao definido", "nao definido", "undefined"})
_NOT_APPLICABLE_SENTINELS = frozenset({"nao se aplica", "not applicable"})


def classify_sentinel(option_text: str) -> str | None:
    """Returns "other", "undefined", "not_applicable" or None (spec §4.1
    Sentinels row)."""
    key = norm(option_text)
    if key in _OTHER_SENTINELS:
        return "other"
    if key in _UNDEFINED_SENTINELS:
        return "undefined"
    if key in _NOT_APPLICABLE_SENTINELS:
        return "not_applicable"
    return None


_PT_MINOR_WORDS = frozenset(
    {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os", "para", "com"}
)


def title_case_pt(text: str) -> str:
    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        if not w:
            out.append(w)
            continue
        lw = strip_accents(w).casefold()
        if i > 0 and lw in _PT_MINOR_WORDS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


# --------------------------------------------------------------------------
# .docx paragraph extraction
# --------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"


@dataclass(frozen=True)
class Paragraph:
    text: str
    style: str | None
    has_numpr: bool


def parse_paragraphs(document_xml: bytes) -> list[Paragraph]:
    """Parse `word/document.xml` bytes into an ordered list of paragraphs. A
    paragraph's text is the concatenation of its w:t descendants (so split
    runs join); its style is w:pPr/w:pStyle/@w:val."""
    root = ET.fromstring(document_xml)
    body = root.find(f"{_W}body")
    if body is None:
        return []
    out: list[Paragraph] = []
    for p in body.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in p.iter(f"{_W}t"))
        style: str | None = None
        has_numpr = False
        p_pr = p.find(f"{_W}pPr")
        if p_pr is not None:
            p_style = p_pr.find(f"{_W}pStyle")
            if p_style is not None:
                style = p_style.get(f"{_W}val")
            has_numpr = p_pr.find(f"{_W}numPr") is not None
        out.append(Paragraph(text=text, style=style, has_numpr=has_numpr))
    return out


def extract_document_xml(docx_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        return zf.read("word/document.xml")


def read_docx_paragraphs(docx_path: Path) -> list[Paragraph]:
    return parse_paragraphs(extract_document_xml(docx_path.read_bytes()))


# --------------------------------------------------------------------------
# Area detection (spec 08 §4.1 "Area")
# --------------------------------------------------------------------------

_AREA_HEADING_STYLES = frozenset({"ttulo1", "titulo1", "heading1", "heading 1"})

# The real document's area headings read "N. PERFIL DE IMPLEMENTAÇÃO FAIR –
# <AREA> [(...)]"; this phrase (accent/case-insensitive) is what tells an
# area heading apart from an unrelated Ttulo1 paragraph earlier in the
# document ("Critério de simplificação adotado").
_AREA_PHRASE_RE = re.compile(
    r"^\s*(?:\d+[.)]\s*)?"
    r"(?:[ÁA]rea\s*\d*\s*[-–—:]\s*)?"
    r"perfil\s+de\s+implementa[cç][aã]o\s+fair",
    re.IGNORECASE,
)
_AREA_SEP_RE = re.compile(r"^\s*[-–—:]\s*")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def normalize_style(style: str | None) -> str:
    return strip_accents(style or "").casefold()


def detect_area_heading(p: Paragraph) -> str | None:
    """Returns the extracted, title-cased area name, or None if `p` is not
    an area heading."""
    if normalize_style(p.style) not in _AREA_HEADING_STYLES:
        return None
    m = _AREA_PHRASE_RE.match(p.text)
    if not m:
        return None
    rest = _AREA_SEP_RE.sub("", p.text[m.end() :], count=1)
    while True:
        stripped = _TRAILING_PAREN_RE.sub("", rest)
        if stripped == rest:
            break
        rest = stripped
    rest = rest.strip(" -–—:")
    return title_case_pt(rest.strip())


def area_slug(name: str) -> str:
    return slugify(strip_accents(name))


@dataclass(frozen=True)
class AreaBlock:
    name: str
    slug: str
    paragraphs: list[Paragraph]


def split_areas(paragraphs: list[Paragraph]) -> list[AreaBlock]:
    headings: list[tuple[int, str]] = []
    for i, p in enumerate(paragraphs):
        name = detect_area_heading(p)
        if name:
            headings.append((i, name))
    blocks: list[AreaBlock] = []
    for idx, (start, name) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(paragraphs)
        blocks.append(
            AreaBlock(name=name, slug=area_slug(name), paragraphs=paragraphs[start + 1 : end])
        )
    return blocks


# --------------------------------------------------------------------------
# Question detection (spec 08 §4.1 "Question"/"Option") + the 21-entry table
# --------------------------------------------------------------------------

# F1.1->F1-metadata, F1.2->F1-data, F2->F2, F3->F3, F4.1/F4.2->F4-metadata/-data,
# A1.1.1/A1.1.2->A1.1-metadata/-data, A1.2.1/A1.2.2->A1.2-metadata/-data, A2->A2,
# I1.1/I1.2, I2.1/I2.2, I3.1/I3.2, R1.1.1/R1.1.2, R1.2.1/R1.2.2 likewise.
DOC_CODE_TO_QUESTION_ID: dict[str, str] = {
    "F1.1": "F1-metadata",
    "F1.2": "F1-data",
    "F2": "F2",
    "F3": "F3",
    "F4.1": "F4-metadata",
    "F4.2": "F4-data",
    "A1.1.1": "A1.1-metadata",
    "A1.1.2": "A1.1-data",
    "A1.2.1": "A1.2-metadata",
    "A1.2.2": "A1.2-data",
    "A2": "A2",
    "I1.1": "I1-metadata",
    "I1.2": "I1-data",
    "I2.1": "I2-metadata",
    "I2.2": "I2-data",
    "I3.1": "I3-metadata",
    "I3.2": "I3-data",
    "R1.1.1": "R1.1-metadata",
    "R1.1.2": "R1.1-data",
    "R1.2.1": "R1.2-metadata",
    "R1.2.2": "R1.2-data",
}

QUESTION_RE = re.compile(
    r"^\s*(F[1-4](\.\d)?|A[12](\.\d)?(\.\d)?|I[123](\.\d)?|R1(\.\d(\.\d)?)?)\s*[.):–-]\s*"
)

_OPTION_PREFIX_RE = re.compile(r"^\s*(?:[☐☑▢□○●•]|-(?!-)|\[\s*\]|\(\s*\))\s*")


class QuestionTableMismatch(Exception):
    """Raised when DOC_CODE_TO_QUESTION_ID doesn't exactly cover the base
    model's question ids (spec 08 §4.1: "a mismatch is a hard exit 2")."""


def assert_doc_code_table(base_model: dict[str, Any]) -> None:
    base_ids = {
        q["id"]
        for section in base_model.get("sections", [])
        for q in section.get("questions", [])
        if isinstance(q, dict) and isinstance(q.get("id"), str)
    }
    table_ids = set(DOC_CODE_TO_QUESTION_ID.values())
    if base_ids != table_ids:
        missing = sorted(base_ids - table_ids)
        extra = sorted(table_ids - base_ids)
        raise QuestionTableMismatch(
            "DOC_CODE_TO_QUESTION_ID does not match the base model's question ids "
            f"(missing from table: {missing}, not in base model: {extra})"
        )


@dataclass
class FoundQuestion:
    doc_code: str
    question_id: str
    text: str
    options: list[str] = field(default_factory=list)


def parse_area_questions(paragraphs: list[Paragraph]) -> tuple[dict[str, FoundQuestion], list[str]]:
    """Walks one area's paragraphs; returns (question_id -> FoundQuestion,
    list of doc codes seen more than once)."""
    found: dict[str, FoundQuestion] = {}
    duplicates: list[str] = []
    current: FoundQuestion | None = None
    for p in paragraphs:
        m = QUESTION_RE.match(p.text)
        if m:
            code = m.group(1)
            qid = DOC_CODE_TO_QUESTION_ID.get(code)
            if qid is None:
                current = None
                continue
            if qid in found:
                duplicates.append(code)
                current = None
                continue
            current = FoundQuestion(doc_code=code, question_id=qid, text=p.text[m.end() :].strip())
            found[qid] = current
            continue
        if current is None:
            continue
        text = p.text.strip()
        if not text:
            continue
        if not (p.has_numpr or _OPTION_PREFIX_RE.match(p.text)):
            continue
        option_text = _OPTION_PREFIX_RE.sub("", p.text, count=1).strip()
        if option_text:
            current.options.append(option_text)
    return found, duplicates


# --------------------------------------------------------------------------
# Option -> FER matching (spec 08 §4.2)
# --------------------------------------------------------------------------


@dataclass
class SeedIndex:
    # norm(label/alias) -> list of (fer_id, fer_type), across all types (steps 1-2 may cross types)
    exact: dict[str, list[tuple[str, str]]]
    # fer_type -> list of (fer_id, raw_text, norm_text) (steps 3-4 never cross types)
    by_type: dict[str, list[tuple[str, str, str]]]


def build_seed_index(seed_entries: list[dict[str, Any]]) -> SeedIndex:
    exact: dict[str, list[tuple[str, str]]] = {}
    by_type: dict[str, list[tuple[str, str, str]]] = {}
    for entry in seed_entries:
        fid = entry.get("id")
        ftype = entry.get("type")
        if not isinstance(fid, str):
            continue
        texts: list[str] = []
        label = entry.get("label") or {}
        if isinstance(label, dict):
            texts.extend(v for v in label.values() if isinstance(v, str) and v)
        aliases = entry.get("aliases") or []
        if isinstance(aliases, list):
            texts.extend(a for a in aliases if isinstance(a, str) and a)
        for raw in texts:
            n = norm(raw)
            if not n:
                continue
            pair = (fid, ftype)
            bucket = exact.setdefault(n, [])
            if pair not in bucket:
                bucket.append(pair)
            if ftype:
                by_type.setdefault(ftype, []).append((fid, raw, n))
    return SeedIndex(exact=exact, by_type=by_type)


def _match_exact(option_norm: str, index: SeedIndex) -> str | None:
    candidates = index.exact.get(option_norm)
    if not candidates:
        return None
    return sorted(set(candidates))[0][0]


def _match_substring(option_norm: str, fer_type: str | None, index: SeedIndex) -> str | None:
    if not fer_type:
        return None
    matches: set[str] = set()
    for fid, _raw, cand_norm in index.by_type.get(fer_type, []):
        if not cand_norm or not option_norm:
            continue
        if cand_norm.startswith(option_norm) or cand_norm.endswith(option_norm):
            matches.add(fid)
            continue
        if re.search(r"(?<!\w)" + re.escape(option_norm) + r"(?!\w)", cand_norm):
            matches.add(fid)
    if not matches:
        return None
    return sorted(matches)[0]


def _match_fuzzy(
    option_norm: str, fer_type: str | None, index: SeedIndex
) -> tuple[str | None, dict[str, Any] | None]:
    """difflib ratio >= 0.90 accepts, highest wins; a runner-up within 0.02
    makes it ambiguous -> unresolved. Returns (resolved_id_or_None,
    best_rejected_candidate_or_None)."""
    if not fer_type:
        return None, None
    candidates = index.by_type.get(fer_type, [])
    if not candidates:
        return None, None
    best_per_id: dict[str, tuple[float, str]] = {}
    for fid, raw, cand_norm in candidates:
        if not cand_norm:
            continue
        ratio = difflib.SequenceMatcher(None, option_norm, cand_norm).ratio()
        prev = best_per_id.get(fid)
        if prev is None or ratio > prev[0]:
            best_per_id[fid] = (ratio, raw)
    if not best_per_id:
        return None, None
    ranked = sorted(
        ((ratio, fid) for fid, (ratio, _raw) in best_per_id.items()), key=lambda x: (-x[0], x[1])
    )
    best_ratio, best_id = ranked[0]
    best_info = {"ferId": best_id, "ratio": round(best_ratio, 4)}
    if best_ratio < 0.90:
        return None, best_info
    if len(ranked) >= 2 and (ranked[0][0] - ranked[1][0]) <= 0.02:
        return None, best_info
    return best_id, None


def resolve_via_seed(
    option_text: str, fer_type: str | None, index: SeedIndex
) -> tuple[str | None, dict[str, Any] | None]:
    """Steps 2-4 of §4.2 (step 1, the option-map override, is applied by the
    caller). Returns (resolved_id, best_rejected_candidate)."""
    n = norm(option_text)
    rid = _match_exact(n, index)
    if rid:
        return rid, None
    rid = _match_substring(n, fer_type, index)
    if rid:
        return rid, None
    rid, best = _match_fuzzy(n, fer_type, index)
    if rid:
        return rid, None
    return None, best


def draft_fer_id(base_url: str, option_norm: str) -> str:
    """{base_url}/fers/draft/<hash16>, hash16 = first 16 hex of sha256(norm(option))."""
    hash16 = hashlib.sha256(option_norm.encode("utf-8")).hexdigest()[:16]
    return f"{base_url.rstrip('/')}/fers/draft/{hash16}"


def is_decided(entry: dict[str, Any]) -> bool:
    """A map entry is "decided" once it carries a real answer: a single
    ferId (including the "skip" sentinel) or a ferIds list. An entry with
    "ferId": null and no "ferIds" is still open for (re-)resolution."""
    return isinstance(entry, dict) and (entry.get("ferId") is not None or bool(entry.get("ferIds")))


def classify_map_entry(entry: dict[str, Any]) -> str:
    """resolved / skipped / ambiguous / unresolved, for the human-readable
    report only (both ambiguous and unresolved become inlineFers drafts;
    skipped options -- generic/placeholder text curated in
    data/fers/aliases-workshop.md -- become neither)."""
    if entry.get("ferId") == "skip":
        return "skipped"
    if entry.get("ferId") is not None or entry.get("ferIds"):
        return "resolved"
    best = entry.get("bestCandidate")
    ratio = best.get("ratio") if isinstance(best, dict) else None
    if isinstance(ratio, (int, float)) and ratio >= 0.80:
        return "ambiguous"
    return "unresolved"


# --------------------------------------------------------------------------
# Encounters + option-map merge (spec 08 §4.2, §4.3 bullet 2)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Encounter:
    area_slug: str
    question_id: str
    fer_type: str | None
    option_text: str


def merge_option_map(
    loaded: dict[str, Any],
    encounters: list[Encounter],
    seed_index: SeedIndex,
    base_url: str,
) -> dict[str, Any]:
    """§4.3 bullet 2: resolved entries are kept as-is; new options are
    appended; an entry whose option text has vanished from the document is
    kept and marked "stale": true. Step 1 of §4.2 (the map always wins,
    including an explicit "ferId": null) is implemented by never
    re-resolving a key that's already present. A "decided" entry (a real
    ferId, the "skip" sentinel, or a ferIds list -- see `is_decided`) is
    always kept as-is; only a still-open "ferId": null entry has its
    diagnostics refreshed."""
    groups: dict[str, list[Encounter]] = {}
    for enc in encounters:
        groups.setdefault(norm(enc.option_text), []).append(enc)

    new_map: dict[str, Any] = {}
    for key, group in groups.items():
        first = group[0]
        if key in loaded:
            entry = loaded[key]
            if isinstance(entry, dict) and is_decided(entry):
                # Decided (human, a previous run, or the aliases-workshop.md
                # seed) -> kept as-is, verbatim.
                kept = dict(entry)
                kept.pop("stale", None)
                new_map[key] = kept
                continue
            # Pinned unresolved (explicit "ferId": null) -> refresh diagnostics,
            # keep the ferId: null pin.
            _resolved_id, best = resolve_via_seed(first.option_text, first.fer_type, seed_index)
            out = {
                "ferId": None,
                "draftFerId": draft_fer_id(base_url, key),
                "questionId": first.question_id,
                "ferType": first.fer_type,
                "seen": sorted({e.area_slug for e in group}),
            }
            if best is not None:
                out["bestCandidate"] = best
            new_map[key] = out
            continue

        # Brand-new option this run -> attempt steps 2-4.
        resolved_id, best = resolve_via_seed(first.option_text, first.fer_type, seed_index)
        if resolved_id is not None:
            new_map[key] = {"ferId": resolved_id}
        else:
            out = {
                "ferId": None,
                "draftFerId": draft_fer_id(base_url, key),
                "questionId": first.question_id,
                "ferType": first.fer_type,
                "seen": sorted({e.area_slug for e in group}),
            }
            if best is not None:
                out["bestCandidate"] = best
            new_map[key] = out

    for key, entry in loaded.items():
        if key not in groups:
            stale = dict(entry)
            stale["stale"] = True
            new_map[key] = stale

    return new_map


# --------------------------------------------------------------------------
# data/fers/aliases-workshop.md: a hand-curated table (written by the
# catalogue agent) of every workshop document option -> FER id(s), with
# generic/placeholder options ("Perfil próprio documentado", "Sem política
# definida", ...) explicitly marked so they never become inlineFers drafts.
# --------------------------------------------------------------------------

_ALIAS_ROW_RE = re.compile(r"^\|(.+)\|(.+)\|$")


def parse_aliases_markdown(text: str) -> dict[str, dict[str, Any]]:
    """Parses the `| Document option text (pt-BR) | Resolves to |` table.
    A row's second cell is either "unmatched: generic" (-> {"ferId":
    "skip"}), one IRI (-> {"ferId": iri}), or several comma-separated IRIs
    (-> {"ferIds": [iri, ...]}) -- some options genuinely match more than
    one catalogue FER (e.g. "ABCD / BioCASe"). Header and separator rows are
    skipped. Keyed by norm(option text), so it merges with option-map.json
    on the same key."""
    out: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        m = _ALIAS_ROW_RE.match(line)
        if not m:
            continue
        option_text, resolution = (m.group(1).strip(), m.group(2).strip())
        if not option_text or set(option_text) <= {"-"}:
            continue  # separator row ("|---|---|")
        if option_text.lower().startswith("document option"):
            continue  # header row
        key = norm(option_text)
        if not key:
            continue
        if resolution.lower().startswith("unmatched"):
            out[key] = {"ferId": "skip"}
            continue
        ids = [part.strip() for part in resolution.split(",")]
        ids = [i for i in ids if i.startswith("http://") or i.startswith("https://")]
        if not ids:
            continue
        out[key] = {"ferId": ids[0]} if len(ids) == 1 else {"ferIds": ids}
    return out


def apply_alias_seed(
    loaded: dict[str, Any], alias_entries: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Seeds `loaded` from the aliases-workshop.md table: a key not already
    "decided" in `loaded` (see `is_decided`) is filled in from the alias
    table; an already-decided entry (a human edit, or a real resolution
    from a previous run) is never overwritten -- option-map.json's own
    entries always have the final say."""
    out = dict(loaded)
    for key, alias_entry in alias_entries.items():
        existing = out.get(key)
        if isinstance(existing, dict) and is_decided(existing):
            continue
        out[key] = dict(alias_entry)
    return out


# --------------------------------------------------------------------------
# Area title translation (11 known CONFOA 2026 areas)
# --------------------------------------------------------------------------

# slug -> (en, es). The document is pt-BR only; this is a simple mapping
# table for the 11 areas known at spec-writing time (spec 08 intro: "5 of 11
# area profiles exist so far and the document will change"). An area not in
# this table falls back to "<pt-BR name> (CONFOA 2026)" (spec 08 §4.3) and
# is flagged in the report for manual translation.
AREA_TRANSLATIONS: dict[str, tuple[str, str]] = {
    "dados-omicos": ("Omics data", "Datos ómicos"),
    "biodiversidade": ("Biodiversity", "Biodiversidad"),
    "agricultura": ("Agriculture", "Agricultura"),
    "saude-publica": ("Public health", "Salud pública"),
    "enfermagem": ("Nursing", "Enfermería"),
    "ciencias-sociais": ("Social sciences", "Ciencias sociales"),
    "patrimonio-cultural": ("Cultural heritage", "Patrimonio cultural"),
    "astronomia": ("Astronomy", "Astronomía"),
    "educacao": ("Education", "Educación"),
    "dados-ambientais": ("Environmental data", "Datos ambientales"),
    "linguistica": ("Linguistics", "Lingüística"),
}


def translate_title(area_name: str, slug: str) -> tuple[str, str, bool]:
    """Returns (en, es, needs_review)."""
    known = AREA_TRANSLATIONS.get(slug)
    if known:
        return known[0], known[1], False
    fallback = f"{area_name} (CONFOA 2026)"
    return fallback, fallback, True


# --------------------------------------------------------------------------
# Model building (spec 08 §4.3 bullet 1)
# --------------------------------------------------------------------------

ATTRIBUTION_TEXT = (
    "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha "
    "Schultes / GO FAIR Foundation, CC BY-SA 4.0."
)

MAX_SUGGESTED_FER_IDS = 12


@dataclass
class QuestionResult:
    question_id: str
    found: bool
    text: str | None
    suggested_ids: list[str]
    truncated_from: int | None
    sentinel_counts: dict[str, int]
    skipped_generic: int = 0


@dataclass
class AreaImportResult:
    name: str
    slug: str
    model_id: str
    questions: dict[str, QuestionResult]
    missing_question_ids: list[str]
    duplicate_doc_codes: list[str]
    content_1_0_0: dict[str, Any]


def base_question_index(base_model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        q["id"]: q
        for section in base_model.get("sections", [])
        for q in section.get("questions", [])
        if isinstance(q, dict) and isinstance(q.get("id"), str)
    }


def build_area_import(
    *,
    area: AreaBlock,
    base_model: dict[str, Any],
    option_map: dict[str, Any],
    canonical_label_by_norm: dict[str, str],
    docx_sha12: str,
    docx_name: str,
    today: str,
) -> AreaImportResult:
    found, duplicates = parse_area_questions(area.paragraphs)
    base_qs = base_question_index(base_model)

    question_results: dict[str, QuestionResult] = {}
    missing: list[str] = []
    inline_fers: dict[str, dict[str, Any]] = {}

    for qid in DOC_CODE_TO_QUESTION_ID.values():
        base_q = base_qs.get(qid, {})
        fer_type = base_q.get("ferType")
        fq = found.get(qid)
        sentinel_counts = {"other": 0, "undefined": 0, "not_applicable": 0}
        if fq is None:
            missing.append(qid)
            question_results[qid] = QuestionResult(
                question_id=qid,
                found=False,
                text=None,
                suggested_ids=[],
                truncated_from=None,
                sentinel_counts=sentinel_counts,
            )
            continue

        ids_ordered: list[str] = []
        seen_ids: set[str] = set()
        skipped_generic = 0
        for opt in fq.options:
            kind = classify_sentinel(opt)
            if kind is not None:
                sentinel_counts[kind] += 1
                continue
            key = norm(opt)
            entry = option_map.get(key)
            if entry is None:
                # Shouldn't happen: merge_option_map is expected to have
                # been run over every encounter first.
                continue
            fer_id = entry.get("ferId")
            if fer_id == "skip":
                # A generic/placeholder option (data/fers/aliases-workshop.md)
                # -> no suggestion, no inlineFers draft.
                skipped_generic += 1
                continue
            resolved_ids = entry.get("ferIds") or ([fer_id] if fer_id else None)
            if resolved_ids is None:
                # Unresolved -> an inlineFers draft, shared across areas by
                # the deterministic draft id (hash of norm(option)).
                draft_id = entry.get("draftFerId") or draft_fer_id("https://fipm.example.org", key)
                inline_fers[draft_id] = {
                    "id": draft_id,
                    "label": {"pt-BR": canonical_label_by_norm.get(key, opt)},
                    "type": entry.get("ferType") or fer_type,
                    "homepage": None,
                }
                resolved_ids = [draft_id]
            for rid in resolved_ids:
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    ids_ordered.append(rid)

        truncated_from = None
        if len(ids_ordered) > MAX_SUGGESTED_FER_IDS:
            truncated_from = len(ids_ordered)
            ids_ordered = ids_ordered[:MAX_SUGGESTED_FER_IDS]

        question_results[qid] = QuestionResult(
            question_id=qid,
            found=True,
            text=fq.text,
            suggested_ids=ids_ordered,
            truncated_from=truncated_from,
            sentinel_counts=sentinel_counts,
            skipped_generic=skipped_generic,
        )

    title_en, title_es, _needs_review = translate_title(area.name, area.slug)
    model_id = f"confoa-2026-{area.slug}"

    # Every one of the base model's 21 question ids is carried over verbatim
    # -- text and help in all languages -- even when the document lacks or
    # truncates that question (spec follow-up: "the matrix relies on shared
    # ids"); only `suggestedFerIds`/`allowFreeText` are added, and only the
    # document's *options* ever differ between the base and a fork, never
    # the question wording (the base's pt-BR was aligned with this document
    # separately, spec 08 §8 Q6).
    sections_out = []
    for section in base_model.get("sections", []):
        questions_out = []
        for q in section.get("questions", []):
            qid = q.get("id")
            result = question_results.get(qid)
            q_out = copy.deepcopy(q)
            q_out["suggestedFerIds"] = result.suggested_ids if result is not None else []
            q_out["allowFreeText"] = True
            questions_out.append(q_out)
        sections_out.append(
            {
                "id": section.get("id"),
                "title": copy.deepcopy(section.get("title")),
                "questions": questions_out,
            }
        )

    content = {
        "id": model_id,
        "version": "1.0.0",
        "status": "draft",
        "license": base_model.get("license"),
        "source": copy.deepcopy(base_model.get("source")),
        "forkedFrom": {"id": base_model.get("id"), "version": base_model.get("version")},
        "attribution": ATTRIBUTION_TEXT,
        "title": {
            "pt-BR": area.name,
            "pt-PT": area.name,
            "en": title_en,
            "es": title_es,
        },
        "description": copy.deepcopy(base_model.get("description")),
        "changelog": [
            {
                "version": "1.0.0",
                "date": today,
                "notes": f"Imported from {docx_name} ({docx_sha12} of the .docx)",
            }
        ],
        "defaultDeclarationStatus": "current",
        "compactDeclarations": True,
        "inlineFers": [inline_fers[k] for k in sorted(inline_fers)],
        "sections": sections_out,
    }

    return AreaImportResult(
        name=area.name,
        slug=area.slug,
        model_id=model_id,
        questions=question_results,
        missing_question_ids=missing,
        duplicate_doc_codes=duplicates,
        content_1_0_0=content,
    )


def _with_version(content: dict[str, Any], version: str) -> dict[str, Any]:
    out = dict(content)
    out["version"] = version
    out["changelog"] = [dict(entry, version=version) for entry in content["changelog"]]
    return out


@dataclass
class WriteDecision:
    version: str
    content: dict[str, Any]
    action: str  # "write" (new or byte-identical rewrite) or "skip" (changed, no --bump)


def decide_output_version(
    out_dir: Path, model_id: str, candidate_1_0_0: dict[str, Any], bump: bool
) -> WriteDecision:
    pattern = re.compile(rf"^{re.escape(model_id)}-(\d+\.\d+\.\d+)\.json$")
    existing: list[str] = []
    if out_dir.exists():
        for f in out_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                existing.append(m.group(1))
    if not existing:
        return WriteDecision(version="1.0.0", content=candidate_1_0_0, action="write")

    existing.sort(key=lambda v: tuple(int(x) for x in v.split(".")))
    latest = existing[-1]
    latest_path = out_dir / f"{model_id}-{latest}.json"
    try:
        latest_doc = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        latest_doc = None

    candidate_at_latest = _with_version(candidate_1_0_0, latest)
    if latest_doc == candidate_at_latest:
        return WriteDecision(version=latest, content=candidate_at_latest, action="write")

    if not bump:
        return WriteDecision(version=latest, content=candidate_at_latest, action="skip")

    major, minor, patch = (int(x) for x in latest.split("."))
    next_version = f"{major}.{minor}.{patch + 1}"
    return WriteDecision(
        version=next_version, content=_with_version(candidate_1_0_0, next_version), action="write"
    )


# --------------------------------------------------------------------------
# Report (spec 08 §4.3 bullet 3)
# --------------------------------------------------------------------------


def render_report(
    *,
    docx_name: str,
    docx_sha12: str,
    base_url: str,
    base_url_is_placeholder: bool,
    generated_on: str,
    areas: list[AreaImportResult],
    option_map: dict[str, Any],
    write_actions: dict[str, str],
    write_versions: dict[str, str],
) -> str:
    lines: list[str] = []
    lines.append("# CONFOA 2026 workshop import report")
    lines.append("")
    lines.append(f"Generated {generated_on}. Source: `{docx_name}` (sha256[:12] `{docx_sha12}`).")
    lines.append(
        f"Base URL: `{base_url}`"
        + (
            " -- PLACEHOLDER, pass a real --base-url before publishing."
            if base_url_is_placeholder
            else "."
        )
    )
    lines.append("")

    total_found = sum(sum(1 for q in a.questions.values() if q.found) for a in areas)
    total_expected = 21 * len(areas)
    total_missing = sum(len(a.missing_question_ids) for a in areas)

    resolved = ambiguous = unresolved = skipped = 0
    for entry in option_map.values():
        kind = classify_map_entry(entry)
        if kind == "resolved":
            resolved += 1
        elif kind == "ambiguous":
            ambiguous += 1
        elif kind == "skipped":
            skipped += 1
        else:
            unresolved += 1
    inline_total = ambiguous + unresolved

    sentinel_totals = {"other": 0, "undefined": 0, "not_applicable": 0}
    skipped_generic_total = 0
    for a in areas:
        for q in a.questions.values():
            for k, v in q.sentinel_counts.items():
                sentinel_totals[k] += v
            skipped_generic_total += q.skipped_generic

    lines.append("## Totals")
    lines.append(f"- Areas detected: {len(areas)}")
    lines.append(
        f"- Questions found / expected: {total_found} / {total_expected} ({total_missing} missing)"
    )
    lines.append(f"- Options resolved to a catalogue FER: {resolved}")
    lines.append(
        f"- Options skipped as generic/placeholder (data/fers/aliases-workshop.md): {skipped} "
        f"({skipped_generic_total} occurrences across areas)"
    )
    lines.append(
        f"- Options as inline FER drafts: {inline_total} "
        f"(ambiguous: {ambiguous}, unresolved: {unresolved})"
    )
    lines.append(
        "- Sentinels dropped: "
        f"Outro={sentinel_totals['other']}, "
        f"Ainda não definido={sentinel_totals['undefined']}, "
        f"Não se aplica={sentinel_totals['not_applicable']}"
    )
    lines.append("")

    for a in areas:
        lines.append(f"## {a.name} (`{a.model_id}`, {write_versions.get(a.model_id, '1.0.0')})")
        action = write_actions.get(a.model_id, "write")
        lines.append(f"- Write action: {action}")
        found_count = sum(1 for q in a.questions.values() if q.found)
        lines.append(f"- Questions found: {found_count}/21")
        if a.missing_question_ids:
            reverse = {v: k for k, v in DOC_CODE_TO_QUESTION_ID.items()}
            missing_codes = ", ".join(
                f"{reverse.get(qid, qid)} ({qid})" for qid in a.missing_question_ids
            )
            lines.append(f"- Missing questions: {missing_codes}")
        if a.duplicate_doc_codes:
            lines.append(f"- Duplicate question headings seen: {', '.join(a.duplicate_doc_codes)}")
        area_skipped = sum(q.skipped_generic for q in a.questions.values())
        if area_skipped:
            lines.append(f"- Options skipped as generic/placeholder: {area_skipped}")
        for qid, q in a.questions.items():
            if not q.found:
                continue
            note = f"  - {qid}: {len(q.suggested_ids)} suggested option(s)"
            if q.truncated_from:
                note += f" (truncated from {q.truncated_from}, see report totals)"
            lines.append(note)
        area_sentinels = {"other": 0, "undefined": 0, "not_applicable": 0}
        for q in a.questions.values():
            for k, v in q.sentinel_counts.items():
                area_sentinels[k] += v
        lines.append(
            "- Sentinels: "
            f"Outro={area_sentinels['other']}, "
            f"Ainda não definido={area_sentinels['undefined']}, "
            f"Não se aplica={area_sentinels['not_applicable']}"
        )
        lines.append("")

    unresolved_entries = [
        (k, v) for k, v in option_map.items() if v.get("ferId") is None and not v.get("stale")
    ]
    if unresolved_entries:
        lines.append("## Unresolved options")
        for key, entry in sorted(unresolved_entries):
            best = entry.get("bestCandidate")
            best_str = (
                f"best rejected candidate `{best['ferId']}` (ratio {best['ratio']})"
                if best
                else "no candidate"
            )
            seen_str = ", ".join(entry.get("seen") or [])
            lines.append(
                f"- `{key}` (question `{entry.get('questionId')}`, type `{entry.get('ferType')}`) "
                f"-> draft `{entry.get('draftFerId')}`, {best_str}, seen in: {seen_str}"
            )
        lines.append("")

    stale_entries = [k for k, v in option_map.items() if v.get("stale")]
    if stale_entries:
        lines.append(
            f"## Stale option-map entries (no longer in the document): {len(stale_entries)}"
        )
        for key in sorted(stale_entries):
            lines.append(f"- `{key}`")
        lines.append("")

    needs_review = [a for a in areas if translate_title(a.name, a.slug)[2]]
    if needs_review:
        lines.append("## Titles needing manual translation review")
        for a in needs_review:
            lines.append(
                f"- {a.model_id}: `en`/`es` machine-generated from the pt-BR name, please review"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=sort_keys) + "\n", encoding="utf-8"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--docx", required=True, type=Path)
    p.add_argument(
        "--base",
        type=Path,
        default=_REPO_ROOT / "data" / "knowledge-models" / "gofair-fip-mini-1.0.0.json",
    )
    p.add_argument("--seed", type=Path, default=_REPO_ROOT / "data" / "fers" / "seed.json")
    p.add_argument(
        "--aliases",
        type=Path,
        default=_REPO_ROOT / "data" / "fers" / "aliases-workshop.md",
        help="hand-curated option -> FER id(s)/skip table; missing file is not an error",
    )
    p.add_argument("--map", type=Path, default=_REPO_ROOT / "data" / "workshop" / "option-map.json")
    p.add_argument("--out", type=Path, default=_REPO_ROOT / "data" / "knowledge-models")
    p.add_argument("--base-url", dest="base_url", default="https://fipm.example.org")
    p.add_argument(
        "--report",
        default=None,
        help='path, or "-" for stdout (default: data/workshop/import-report-<date>.md)',
    )
    p.add_argument("--bump", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        docx_bytes = args.docx.read_bytes()
    except OSError as exc:
        print(f"error: cannot read --docx {args.docx}: {exc}", file=sys.stderr)
        return 2
    try:
        base_model = _read_json(args.base)
    except OSError as exc:
        print(f"error: cannot read --base {args.base}: {exc}", file=sys.stderr)
        return 2
    try:
        seed_entries = _read_json(args.seed)
    except OSError as exc:
        print(f"error: cannot read --seed {args.seed}: {exc}", file=sys.stderr)
        return 2
    try:
        loaded_map = _read_json(args.map) if args.map.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read --map {args.map}: {exc}", file=sys.stderr)
        return 2
    try:
        alias_entries = (
            parse_aliases_markdown(args.aliases.read_text(encoding="utf-8"))
            if args.aliases.exists()
            else {}
        )
    except OSError as exc:
        print(f"error: cannot read --aliases {args.aliases}: {exc}", file=sys.stderr)
        return 2
    loaded_map = apply_alias_seed(loaded_map, alias_entries)

    try:
        assert_doc_code_table(base_model)
    except QuestionTableMismatch as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        document_xml = extract_document_xml(docx_bytes)
        paragraphs = parse_paragraphs(document_xml)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        print(f"error: cannot parse {args.docx} as a .docx: {exc}", file=sys.stderr)
        return 2

    docx_sha12 = hashlib.sha256(docx_bytes).hexdigest()[:12]
    today = date.today().isoformat()
    docx_name = args.docx.name

    areas_blocks = split_areas(paragraphs)
    seed_index = build_seed_index(seed_entries)
    base_qs = base_question_index(base_model)

    # Pass 1: collect every non-sentinel option encountered, in document order.
    encounters: list[Encounter] = []
    canonical_label_by_norm: dict[str, str] = {}
    per_area_found: dict[str, dict[str, FoundQuestion]] = {}
    for block in areas_blocks:
        found, _dupes = parse_area_questions(block.paragraphs)
        per_area_found[block.slug] = found
        for qid, fq in found.items():
            fer_type = base_qs.get(qid, {}).get("ferType")
            for opt in fq.options:
                if classify_sentinel(opt) is not None:
                    continue
                key = norm(opt)
                canonical_label_by_norm.setdefault(key, opt)
                encounters.append(
                    Encounter(
                        area_slug=block.slug, question_id=qid, fer_type=fer_type, option_text=opt
                    )
                )

    merged_map = merge_option_map(loaded_map, encounters, seed_index, args.base_url)

    # Pass 2: build each area's model content using the now-final option map.
    area_results: list[AreaImportResult] = []
    for block in areas_blocks:
        area_results.append(
            build_area_import(
                area=block,
                base_model=base_model,
                option_map=merged_map,
                canonical_label_by_norm=canonical_label_by_norm,
                docx_sha12=docx_sha12,
                docx_name=docx_name,
                today=today,
            )
        )

    known_fer_ids = {
        e["id"] for e in seed_entries if isinstance(e, dict) and isinstance(e.get("id"), str)
    }

    write_actions: dict[str, str] = {}
    write_versions: dict[str, str] = {}
    validation_errors: dict[str, list[dict]] = {}

    for area in area_results:
        decision = decide_output_version(args.out, area.model_id, area.content_1_0_0, args.bump)
        write_actions[area.model_id] = decision.action
        write_versions[area.model_id] = decision.version

        errors = validate_content(decision.content, known_fer_ids=known_fer_ids)
        if errors:
            validation_errors[area.model_id] = errors
            continue

        if decision.action == "write" and not args.dry_run:
            out_path = args.out / f"{area.model_id}-{decision.version}.json"
            _write_json(out_path, decision.content)

    if not args.dry_run:
        _write_json(args.map, merged_map, sort_keys=True)

    base_url_is_placeholder = args.base_url == "https://fipm.example.org"
    generated_on = today
    report_text = render_report(
        docx_name=docx_name,
        docx_sha12=docx_sha12,
        base_url=args.base_url,
        base_url_is_placeholder=base_url_is_placeholder,
        generated_on=generated_on,
        areas=area_results,
        option_map=merged_map,
        write_actions=write_actions,
        write_versions=write_versions,
    )

    if validation_errors:
        report_text += "\n## Validation errors (model NOT written)\n"
        for model_id, errors in validation_errors.items():
            report_text += f"\n### {model_id}\n"
            for e in errors:
                report_text += f"- `{e['path']}` {e['code']}: {e['message']}\n"

    if args.report == "-":
        print(report_text)
    else:
        report_path = (
            Path(args.report)
            if args.report
            else (_REPO_ROOT / "data" / "workshop" / f"import-report-{today}.md")
        )
        if not args.dry_run:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report_text, encoding="utf-8")
        else:
            print(report_text)

    if validation_errors:
        print(
            f"error: {len(validation_errors)} model(s) failed validate_content, see report",
            file=sys.stderr,
        )
        return 2

    total_missing = sum(len(a.missing_question_ids) for a in area_results)
    total_unresolved = sum(
        1 for v in merged_map.values() if v.get("ferId") is None and not v.get("stale")
    )
    if args.strict and (total_missing > 0 or total_unresolved > 0):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
