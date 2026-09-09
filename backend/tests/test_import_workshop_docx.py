"""AC18 (spec 08-workshop-picklists.md §4, §6): `scripts/import-workshop-docx.py`
against a synthetic .docx built in-memory with `zipfile`.

The script lives outside the `fipm` package (it's a standalone stdlib-only
tool, spec 08 §4), so it's loaded here via `importlib` under the module name
`import_workshop_docx` (registered in `sys.modules` first -- required for its
`@dataclass` definitions to resolve their own module at class-creation time).
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import sys
import xml.sax.saxutils as saxutils
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "import-workshop-docx.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("import_workshop_docx", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_workshop_docx"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def iwd():
    return _load_module()


# --------------------------------------------------------------------------
# .docx fixture builder
# --------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _para_xml(text: str, style: str | None = None, split_runs: bool = False) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    if split_runs and len(text) > 2:
        # Simulate Word splitting a paragraph's text across several runs
        # (spec 08 §4: "a paragraph's text is the concatenation of its w:t
        # descendants, so split runs join").
        mid = len(text) // 2
        parts = [text[:mid], text[mid:]]
    else:
        parts = [text]
    runs = "".join(
        f'<w:r><w:t xml:space="preserve">{saxutils.escape(p)}</w:t></w:r>' for p in parts
    )
    return f"<w:p>{style_xml}{runs}</w:p>"


def _document_xml(paragraphs: list[tuple[str, str | None]]) -> bytes:
    body = "".join(_para_xml(text, style) for text, style in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W_NS}"><w:body>{body}</w:body></w:document>'
    )
    return xml.encode("utf-8")


def _docx_bytes(paragraphs: list[tuple[str, str | None]]) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        zf.writestr("word/document.xml", _document_xml(paragraphs))
    return buf.getvalue()


# --------------------------------------------------------------------------
# Synthetic base model + seed (21 real GO FAIR question ids, minimal content)
# --------------------------------------------------------------------------

OMIT_CODES = {"F3", "A2"}  # deliberately absent from the fixture doc -> "missing"
RICH_CODES = {"F1.1", "I2.1"}  # get the full 2-known + 1-unknown + sentinels treatment


def _base_model(doc_code_to_qid: dict[str, str]) -> dict:
    by_letter: dict[str, list[str]] = {}
    for qid in doc_code_to_qid.values():
        by_letter.setdefault(qid[0], []).append(qid)
    sections = []
    for letter in ("F", "A", "I", "R"):
        qs = []
        for qid in by_letter.get(letter, []):
            fer_type = "structured-vocabulary" if qid == "I2-metadata" else "identifier-service"
            qs.append(
                {
                    "id": qid,
                    "text": {
                        "en": f"Base question text for {qid}",
                        "pt-BR": f"Texto base de {qid}",
                    },
                    "ferType": fer_type,
                }
            )
        sections.append({"id": letter, "title": {"en": f"{letter} section"}, "questions": qs})
    return {
        "id": "test-base",
        "version": "1.0.0",
        "status": "published",
        "license": "CC-BY-SA-4.0",
        "source": {"name": "Test source", "url": "https://example.org/source"},
        "title": {"en": "Test base model"},
        "description": {"en": "A minimal 21-question base model for the importer tests."},
        "changelog": [{"version": "1.0.0", "date": "2026-01-01", "notes": "Initial."}],
        "sections": sections,
    }


SEED_ENTRIES = [
    {"id": "https://www.doi.org/", "label": {"en": "DOI"}, "type": "identifier-service"},
    {
        "id": "https://www.handle.net/",
        "label": {"en": "Handle System"},
        "type": "identifier-service",
    },
    {"id": "https://schema.org/", "label": {"en": "Schema.org"}, "type": "structured-vocabulary"},
    {
        "id": "https://www.wikidata.org/",
        "label": {"en": "Wikidata"},
        "type": "structured-vocabulary",
    },
]

UNKNOWN_F11_TEXT = "Vocabulário Institucional Não Catalogado XPTO123"
UNKNOWN_I21_TEXT = "Esquema Proprietário Interno da Unidade ZZZ789"


def _area_paragraphs(iwd, area_num: int, area_name: str) -> list[tuple[str, str | None]]:
    paras: list[tuple[str, str | None]] = [
        (f"{area_num}. PERFIL DE IMPLEMENTAÇÃO FAIR – {area_name}", "Ttulo1")
    ]
    for code in iwd.DOC_CODE_TO_QUESTION_ID:
        if code in OMIT_CODES:
            continue
        paras.append((f"{code}. Texto da pergunta {code} no documento", None))
        if code == "F1.1":
            paras.append(("Frase de apoio explicando a pergunta, não é uma opção.", None))
            paras.append(("☐ DOI", None))
            paras.append(("☐ Handle System", None))
            paras.append((f"☐ {UNKNOWN_F11_TEXT}", None))
            paras.append(("☐ Outro", None))
            paras.append(("☐ Não se aplica", None))
        elif code == "I2.1":
            paras.append(("☐ Schema.org", None))
            paras.append(("☐ Wikidata", None))
            paras.append((f"☐ {UNKNOWN_I21_TEXT}", None))
            paras.append(("☐ Outro", None))
            paras.append(("☐ Não se aplica", None))
    return paras


def _build_fixture_docx(iwd, *, edited: bool = False) -> bytes:
    unknown_f11 = UNKNOWN_F11_TEXT + (" EDITADO" if edited else "")
    paras: list[tuple[str, str | None]] = []
    for area_num, area_name in ((1, "ÁREA UM"), (2, "ÁREA DOIS")):
        block = _area_paragraphs(iwd, area_num, area_name)
        if edited:
            block = [(t.replace(UNKNOWN_F11_TEXT, unknown_f11), s) for t, s in block]
        paras.extend(block)
    return _docx_bytes(paras)


# --------------------------------------------------------------------------
# Pure-function unit tests
# --------------------------------------------------------------------------


def test_norm_normalises_accents_case_parens_and_punctuation(iwd):
    assert iwd.norm("  Dublin Core (DC Terms)!  ") == "dublin core"
    assert iwd.norm("São Paulo") == "sao paulo"
    assert iwd.norm("DOI") == iwd.norm("doi")


def test_classify_sentinel(iwd):
    assert iwd.classify_sentinel("Outro") == "other"
    assert iwd.classify_sentinel("outros") == "other"
    assert iwd.classify_sentinel("Ainda não definido") == "undefined"
    assert iwd.classify_sentinel("Não se aplica") == "not_applicable"
    assert iwd.classify_sentinel("DOI") is None


def test_detect_area_heading_ignores_unrelated_ttulo1(iwd):
    decoy = iwd.Paragraph(text="Critério de simplificação adotado", style="Ttulo1", has_numpr=False)
    assert iwd.detect_area_heading(decoy) is None

    heading = iwd.Paragraph(
        text="1. PERFIL DE IMPLEMENTAÇÃO FAIR – DADOS ÔMICOS (EXEMPLO DEMONSTRATIVO)",
        style="Ttulo1",
        has_numpr=False,
    )
    assert iwd.detect_area_heading(heading) == "Dados Ômicos"

    not_heading_style = iwd.Paragraph(
        text="1. PERFIL DE IMPLEMENTAÇÃO FAIR – BIODIVERSIDADE", style=None, has_numpr=False
    )
    assert iwd.detect_area_heading(not_heading_style) is None


def test_parse_paragraphs_reads_text_and_style(iwd):
    doc_xml = _document_xml([("Hello world", None), ("F1.1. Some heading", "Ttulo2")])
    paras = iwd.parse_paragraphs(doc_xml)
    assert paras[0].text == "Hello world"
    assert paras[0].style is None
    assert paras[1].style == "Ttulo2"


def test_parse_paragraphs_join_split_runs(iwd):
    # A paragraph's text is the concatenation of its w:t descendants, so
    # split runs (as Word commonly produces, e.g. after a spelling edit)
    # must join back into one string.
    body = _para_xml("split-run-text", split_runs=True)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W_NS}"><w:body>{body}</w:body></w:document>'
    ).encode()
    paras = iwd.parse_paragraphs(xml)
    assert len(paras) == 1
    assert paras[0].text == "split-run-text"


def test_parse_area_questions_extracts_options_and_strips_glyphs(iwd, tmp_path):
    paragraphs_raw = [
        ("F1.1. Identificadores persistentes", None),
        ("Frase de apoio, não é opção.", None),
        ("☐ DOI", None),
        ("☐ Handle System", None),
        ("☐ Outro", None),
        ("F2. Esquemas de metadados", None),
        ("☐ ISA-Tab", None),
    ]
    from import_workshop_docx import Paragraph

    paragraphs = [Paragraph(text=t, style=s, has_numpr=False) for t, s in paragraphs_raw]
    found, dupes = iwd.parse_area_questions(paragraphs)
    assert dupes == []
    assert set(found) == {"F1-metadata", "F2"}
    f1 = found["F1-metadata"]
    assert f1.text == "Identificadores persistentes"
    assert f1.options == ["DOI", "Handle System", "Outro"]
    assert found["F2"].options == ["ISA-Tab"]


def test_assert_doc_code_table_matches_and_detects_mismatch(iwd):
    base = _base_model(iwd.DOC_CODE_TO_QUESTION_ID)
    iwd.assert_doc_code_table(base)  # does not raise

    broken = json.loads(json.dumps(base))
    broken["sections"][0]["questions"][0]["id"] = "not-a-real-id"
    with pytest.raises(iwd.QuestionTableMismatch):
        iwd.assert_doc_code_table(broken)


def test_resolve_via_seed_exact_and_substring(iwd):
    index = iwd.build_seed_index(SEED_ENTRIES)
    rid, best = iwd.resolve_via_seed("DOI", "identifier-service", index)
    assert rid == "https://www.doi.org/"
    assert best is None

    # substring: option is a whole-word prefix of a longer same-type label
    index2 = iwd.build_seed_index(
        [{"id": "https://x/", "label": {"en": "Dublin Core (DC Terms)"}, "type": "metadata-schema"}]
    )
    rid2, best2 = iwd.resolve_via_seed("Dublin Core", "metadata-schema", index2)
    assert rid2 == "https://x/"


def test_resolve_via_seed_ambiguity_thresholds(iwd):
    """AC18: ambiguity at ratio 0.89/0.90/0.91 asserted. Two 100-char strings
    of otherwise-unique characters, differing only by substitutions (each to
    another character used nowhere else) at k positions, give a difflib
    ratio of exactly (100-k)/100. Two difflib pitfalls to dodge: a *repeated*
    filler character (e.g. "x"*100) makes the greedy longest-match search
    anchor on one big block and starve the rest, so the ratio would not
    reflect the edit count; and at length >= 200 the "autojunk" heuristic
    starts discarding any character that recurs often, which any small
    alphabet repeated to fill 200+ chars would trigger. Private Use Area
    code points (each used exactly once) and a length of 100 avoid both."""

    candidate = "".join(chr(0xE000 + i) for i in range(100))

    def make(k: int) -> str:
        s = list(candidate)
        step = 100 // k
        for i in range(k):
            s[step * i] = chr(0xE100 + i)
        return "".join(s)

    opt_91 = make(9)
    opt_90 = make(10)
    opt_89 = make(11)

    # Sanity-check the actual difflib ratios before trusting the boundary assertions.
    assert round(difflib.SequenceMatcher(None, opt_91, candidate).ratio(), 4) == 0.91
    assert round(difflib.SequenceMatcher(None, opt_90, candidate).ratio(), 4) == 0.90
    assert round(difflib.SequenceMatcher(None, opt_89, candidate).ratio(), 4) == 0.89

    index = iwd.build_seed_index(
        [{"id": "https://example.org/fer/x", "label": {"en": candidate}, "type": "t"}]
    )

    rid, best = iwd.resolve_via_seed(opt_91, "t", index)
    assert rid == "https://example.org/fer/x" and best is None

    rid, best = iwd.resolve_via_seed(opt_90, "t", index)
    assert rid == "https://example.org/fer/x" and best is None

    rid, best = iwd.resolve_via_seed(opt_89, "t", index)
    assert rid is None
    assert best is not None and best["ratio"] == 0.89


def test_merge_option_map_shared_draft_across_areas(iwd):
    index = iwd.build_seed_index(SEED_ENTRIES)
    encounters = [
        iwd.Encounter(
            area_slug="area-um",
            question_id="F1-metadata",
            fer_type="identifier-service",
            option_text=UNKNOWN_F11_TEXT,
        ),
        iwd.Encounter(
            area_slug="area-dois",
            question_id="F1-metadata",
            fer_type="identifier-service",
            option_text=UNKNOWN_F11_TEXT,
        ),
    ]
    merged = iwd.merge_option_map({}, encounters, index, "https://fipm.example.org")
    key = iwd.norm(UNKNOWN_F11_TEXT)
    entry = merged[key]
    assert entry["ferId"] is None
    assert entry["draftFerId"] == iwd.draft_fer_id("https://fipm.example.org", key)
    assert entry["seen"] == ["area-dois", "area-um"]


def test_merge_option_map_keeps_resolved_entry_as_is(iwd):
    index = iwd.build_seed_index(SEED_ENTRIES)
    key = iwd.norm("API REST")
    loaded = {key: {"ferId": "https://human-chosen.example.org/"}}
    encounters = [
        iwd.Encounter(
            area_slug="area-um",
            question_id="F1-metadata",
            fer_type="identifier-service",
            option_text="API REST",
        )
    ]
    merged = iwd.merge_option_map(loaded, encounters, index, "https://fipm.example.org")
    assert merged[key] == {"ferId": "https://human-chosen.example.org/"}


def test_merge_option_map_marks_vanished_entries_stale(iwd):
    index = iwd.build_seed_index(SEED_ENTRIES)
    loaded = {"gone-option": {"ferId": "https://x/"}}
    merged = iwd.merge_option_map(loaded, [], index, "https://fipm.example.org")
    assert merged["gone-option"]["stale"] is True
    assert merged["gone-option"]["ferId"] == "https://x/"


# --------------------------------------------------------------------------
# data/fers/aliases-workshop.md: "skip" (generic options) + multi-IRI rows
# --------------------------------------------------------------------------

ALIASES_MD_SAMPLE = """\
# Workshop document option -> FER id mapping

| Document option text (pt-BR) | Resolves to |
|---|---|
| Perfil próprio documentado | unmatched: generic |
| Sem política definida | unmatched: generic |
| ABCD / BioCASe | https://abcd.tdwg.org/, https://www.biocase.org/ |
| DOI | https://www.doi.org/ |

**Totals:** 4 unique options; 2 resolve to a FER id; 2 are generic/placeholder.
"""


def test_parse_aliases_markdown(iwd):
    entries = iwd.parse_aliases_markdown(ALIASES_MD_SAMPLE)
    assert entries[iwd.norm("Perfil próprio documentado")] == {"ferId": "skip"}
    assert entries[iwd.norm("Sem política definida")] == {"ferId": "skip"}
    assert entries[iwd.norm("DOI")] == {"ferId": "https://www.doi.org/"}
    assert entries[iwd.norm("ABCD / BioCASe")] == {
        "ferIds": ["https://abcd.tdwg.org/", "https://www.biocase.org/"]
    }
    # header, separator and totals lines never become entries.
    assert iwd.norm("Document option text (pt-BR)") not in entries
    assert len(entries) == 4


def test_apply_alias_seed_never_overrides_a_decided_entry(iwd):
    alias_entries = {
        "opt-a": {"ferId": "skip"},
        "opt-b": {"ferId": "https://from-alias.example.org/"},
    }
    loaded = {"opt-b": {"ferId": "https://human-chosen.example.org/"}}  # already decided
    out = iwd.apply_alias_seed(loaded, alias_entries)
    assert out["opt-a"] == {"ferId": "skip"}
    assert out["opt-b"] == {"ferId": "https://human-chosen.example.org/"}  # untouched


def test_apply_alias_seed_fills_an_open_null_entry(iwd):
    loaded = {"opt-a": {"ferId": None, "draftFerId": "https://x/fers/draft/abc"}}
    alias_entries = {"opt-a": {"ferId": "skip"}}
    out = iwd.apply_alias_seed(loaded, alias_entries)
    assert out["opt-a"] == {"ferId": "skip"}


def test_is_decided(iwd):
    assert iwd.is_decided({"ferId": "https://x/"}) is True
    assert iwd.is_decided({"ferId": "skip"}) is True
    assert iwd.is_decided({"ferIds": ["https://x/", "https://y/"]}) is True
    assert iwd.is_decided({"ferId": None}) is False
    assert iwd.is_decided({"ferId": None, "draftFerId": "https://x/fers/draft/abc"}) is False


# --------------------------------------------------------------------------
# End-to-end (AC18): main() over a synthetic 2-area docx
# --------------------------------------------------------------------------


@pytest.fixture()
def ac18_env(iwd, tmp_path):
    base_model = _base_model(iwd.DOC_CODE_TO_QUESTION_ID)
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base_model), encoding="utf-8")

    seed_path = tmp_path / "seed.json"
    seed_path.write_text(json.dumps(SEED_ENTRIES), encoding="utf-8")

    docx_path = tmp_path / "PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx"
    docx_path.write_bytes(_build_fixture_docx(iwd))

    return {
        "base": base_path,
        "seed": seed_path,
        "docx": docx_path,
        "map": tmp_path / "option-map.json",
        # Points at a file that doesn't exist by default -- isolates tests
        "aliases": tmp_path / "aliases-workshop.md",
        # from the real, growing data/fers/aliases-workshop.md. main() treats
        # a missing --aliases file as "nothing to seed", not an error.
        "out": tmp_path / "out",
        "report": tmp_path / "report.md",
        "tmp_path": tmp_path,
    }


def _run(iwd, env, *extra_args):
    args = [
        "--docx",
        str(env["docx"]),
        "--base",
        str(env["base"]),
        "--seed",
        str(env["seed"]),
        "--aliases",
        str(env["aliases"]),
        "--map",
        str(env["map"]),
        "--out",
        str(env["out"]),
        "--report",
        str(env["report"]),
        *extra_args,
    ]
    return iwd.main(args)


def test_ac18_full_import(iwd, ac18_env):
    from fipm.km_content import validate_content

    rc = _run(iwd, ac18_env)
    assert rc == 0

    model_files = sorted(ac18_env["out"].glob("confoa-2026-*-1.0.0.json"))
    assert len(model_files) == 2

    known_fer_ids = {e["id"] for e in SEED_ENTRIES}
    docs = []
    for f in model_files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        docs.append(doc)
        errors = validate_content(doc, known_fer_ids=known_fer_ids)
        assert errors == [], errors
        assert doc["status"] == "draft"
        assert doc["defaultDeclarationStatus"] == "current"
        assert doc["compactDeclarations"] is True
        assert doc["forkedFrom"] == {"id": "test-base", "version": "1.0.0"}

        by_id = {q["id"]: q for s in doc["sections"] for q in s["questions"]}
        # All 21 base question ids are always present -- the matrix relies
        # on shared ids across forks -- even though 2 codes (F3, A2) are
        # missing from this fixture's document.
        assert set(by_id) == set(iwd.DOC_CODE_TO_QUESTION_ID.values())
        # allowFreeText is set true everywhere; hidden is never introduced.
        assert all(q["allowFreeText"] is True for q in by_id.values())
        assert all("hidden" not in q for q in by_id.values())
        # Only options differ from the base: text/help are copied verbatim
        # in every language, never replaced by the document's short heading,
        # even for a question the document *did* find options for.
        base_model = _base_model(iwd.DOC_CODE_TO_QUESTION_ID)
        base_by_id = {q["id"]: q for s in base_model["sections"] for q in s["questions"]}
        assert by_id["F1-metadata"]["text"] == base_by_id["F1-metadata"]["text"]
        assert by_id["F1-metadata"]["text"]["pt-BR"] == "Texto base de F1-metadata"
        # Sentinels dropped: F1-metadata got 2 known + 1 unknown draft, not 5.
        assert len(by_id["F1-metadata"]["suggestedFerIds"]) == 3
        assert "https://www.doi.org/" in by_id["F1-metadata"]["suggestedFerIds"]
        assert "https://www.handle.net/" in by_id["F1-metadata"]["suggestedFerIds"]
        assert len(by_id["I2-metadata"]["suggestedFerIds"]) == 3
        assert "https://schema.org/" in by_id["I2-metadata"]["suggestedFerIds"]
        assert "https://www.wikidata.org/" in by_id["I2-metadata"]["suggestedFerIds"]
        # Missing questions (omitted from the doc) keep base text and no suggestions.
        assert by_id["F3"]["suggestedFerIds"] == []
        assert by_id["F3"]["text"]["pt-BR"] == "Texto base de F3"
        assert by_id["A2"]["suggestedFerIds"] == []

    # Shared draft IRI for the unknown F1.1 option seen in both areas.
    f1_drafts = [
        [fid for fid in q["suggestedFerIds"] if "draft" in fid]
        for d in docs
        for s in d["sections"]
        for q in s["questions"]
        if q["id"] == "F1-metadata"
    ]
    assert len(f1_drafts[0]) == 1 and len(f1_drafts[1]) == 1
    assert f1_drafts[0][0] == f1_drafts[1][0]

    # option-map.json: unresolved entry shape.
    option_map = json.loads(ac18_env["map"].read_text(encoding="utf-8"))
    key = iwd.norm(UNKNOWN_F11_TEXT)
    entry = option_map[key]
    assert entry["ferId"] is None
    assert "draftFerId" in entry
    assert set(entry["seen"]) == {"area-um", "area-dois"}

    # report mentions both areas and missing questions.
    report_text = ac18_env["report"].read_text(encoding="utf-8")
    assert "Área Um" in report_text or "área-um" in report_text.lower()
    assert "missing" in report_text.lower()


def test_ac18_missing_question_warnings_per_area(iwd, ac18_env):
    rc = _run(iwd, ac18_env)
    assert rc == 0
    for f in sorted(ac18_env["out"].glob("confoa-2026-*-1.0.0.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        by_id = {q["id"]: q for s in doc["sections"] for q in s["questions"]}
        missing = [
            qid
            for qid in ("F3", "A2")
            if by_id[qid]["suggestedFerIds"] == []
            and by_id[qid]["text"]["pt-BR"].startswith("Texto base")
        ]
        assert len(missing) == 2


def test_ac18_rerun_is_byte_identical(iwd, ac18_env):
    rc = _run(iwd, ac18_env)
    assert rc == 0
    before = {f.name: f.read_bytes() for f in ac18_env["out"].glob("*.json")}
    before_map = ac18_env["map"].read_bytes()

    rc2 = _run(iwd, ac18_env)
    assert rc2 == 0
    after = {f.name: f.read_bytes() for f in ac18_env["out"].glob("*.json")}
    after_map = ac18_env["map"].read_bytes()

    assert before == after
    assert before_map == after_map


def test_ac18_bump_writes_new_version_and_keeps_old(iwd, ac18_env):
    rc = _run(iwd, ac18_env)
    assert rc == 0
    before = {f.name: f.read_bytes() for f in ac18_env["out"].glob("confoa-2026-*-1.0.0.json")}
    assert len(before) == 2

    ac18_env["docx"].write_bytes(_build_fixture_docx(iwd, edited=True))
    rc2 = _run(iwd, ac18_env, "--bump")
    assert rc2 == 0

    bumped = sorted(ac18_env["out"].glob("confoa-2026-*-1.0.1.json"))
    assert len(bumped) == 2
    for name, data in before.items():
        assert (ac18_env["out"] / name).read_bytes() == data  # kept untouched


def test_ac18_strict_exits_1(iwd, ac18_env):
    rc = _run(iwd, ac18_env, "--strict")
    assert rc == 1


def test_ac18_dry_run_writes_nothing(iwd, ac18_env):
    rc = _run(iwd, ac18_env, "--dry-run")
    assert rc == 0
    assert not ac18_env["out"].exists() or not any(ac18_env["out"].glob("*.json"))
    assert not ac18_env["map"].exists()


def test_ac18_aliases_md_skips_generic_and_resolves_multi_iri(iwd, ac18_env):
    """Coordinator follow-up: a generic/placeholder option marked in
    data/fers/aliases-workshop.md must become neither a suggestion nor an
    inlineFers draft, and a row with several comma-separated IRIs must add
    all of them."""
    aliases_text = "\n".join(
        [
            "| Document option text (pt-BR) | Resolves to |",
            "|---|---|",
            f"| {UNKNOWN_I21_TEXT} | unmatched: generic |",
            f"| {UNKNOWN_F11_TEXT} | https://schema.org/, https://www.wikidata.org/ |",
        ]
    )
    ac18_env["aliases"].write_text(aliases_text, encoding="utf-8")

    rc = _run(iwd, ac18_env)
    assert rc == 0

    docs = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(ac18_env["out"].glob("confoa-2026-*-1.0.0.json"))
    ]
    for doc in docs:
        by_id = {q["id"]: q for s in doc["sections"] for q in s["questions"]}
        # UNKNOWN_I21_TEXT is now "skip": only the 2 known options remain.
        assert by_id["I2-metadata"]["suggestedFerIds"] == [
            "https://schema.org/",
            "https://www.wikidata.org/",
        ]
        # UNKNOWN_F11_TEXT now resolves to 2 real ids instead of a draft.
        assert by_id["F1-metadata"]["suggestedFerIds"] == [
            "https://www.doi.org/",
            "https://www.handle.net/",
            "https://schema.org/",
            "https://www.wikidata.org/",
        ]
        assert doc["inlineFers"] == []  # no drafts remain at all

    option_map = json.loads(ac18_env["map"].read_text(encoding="utf-8"))
    assert option_map[iwd.norm(UNKNOWN_I21_TEXT)] == {"ferId": "skip"}
    assert option_map[iwd.norm(UNKNOWN_F11_TEXT)] == {
        "ferIds": ["https://schema.org/", "https://www.wikidata.org/"]
    }

    report_text = ac18_env["report"].read_text(encoding="utf-8")
    assert "skipped as generic" in report_text.lower()


def test_ac18_missing_aliases_file_is_not_an_error(iwd, ac18_env):
    assert not ac18_env["aliases"].exists()
    rc = _run(iwd, ac18_env)
    assert rc == 0
