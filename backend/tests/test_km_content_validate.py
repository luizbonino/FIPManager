"""AC11 (spec 04 §6): `validate_content` unit tests against a fixture table
(duplicate question id, unknown ferType, unknown principle, missing en, bad
scope, 301 questions) plus the real gofair-fip-mini-1.0.0.json file (must
validate clean); and `python -m fipm import-data` still reports all-skipped
on a warm DB now that validation is delegated to this module."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fipm.config import Settings
from fipm.km_content import validate_content

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _base_doc() -> dict:
    return {
        "title": {"en": "Test model"},
        "description": {"en": "A test model"},
        "sections": [
            {
                "id": "sec1",
                "title": {"en": "Section 1"},
                "questions": [
                    {
                        "id": "q1",
                        "principle": "F1",
                        "scope": "metadata",
                        "text": {"en": "Question 1"},
                        "ferType": "identifier-service",
                        "required": False,
                        "allowMultiple": True,
                    }
                ],
            }
        ],
    }


def _find(errors, path, code):
    return next((e for e in errors if e["path"] == path and e["code"] == code), None)


def test_valid_doc_has_no_errors(settings):
    assert validate_content(_base_doc(), settings=settings) == []


def test_duplicate_question_id(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"].append(
        {"id": "q1", "text": {"en": "Question 1 again"}, "required": False, "allowMultiple": True}
    )
    errors = validate_content(doc, settings=settings)
    hit = _find(errors, "sections[0].questions[1].id", "duplicate_question_id")
    assert hit is not None, errors


def test_unknown_fer_type(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["ferType"] = "not-a-real-fer-type"
    errors = validate_content(doc, settings=settings)
    hit = _find(errors, "sections[0].questions[0].ferType", "unknown_fer_type")
    assert hit is not None, errors


def test_unknown_principle(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["principle"] = "X9"
    errors = validate_content(doc, settings=settings)
    hit = _find(errors, "sections[0].questions[0].principle", "unknown_principle")
    assert hit is not None, errors


def test_missing_en(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["text"] = {"pt-PT": "Pergunta 1"}
    errors = validate_content(doc, settings=settings)
    hit = _find(errors, "sections[0].questions[0].text", "missing_en")
    assert hit is not None, errors


def test_bad_scope(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["scope"] = "nonsense"
    errors = validate_content(doc, settings=settings)
    hit = _find(errors, "sections[0].questions[0].scope", "invalid_value")
    assert hit is not None, errors


def test_301_questions_too_many(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"] = [
        {"id": f"q{i}", "text": {"en": f"Question {i}"}, "required": False, "allowMultiple": True}
        for i in range(301)
    ]
    errors = validate_content(doc, settings=settings)
    hit = _find(errors, "sections", "too_many")
    assert hit is not None, errors


def test_empty_fer_type_taxonomy_skips_the_rule_and_warns_once(monkeypatch, caplog, tmp_path):
    """Review finding 8: a missing/empty data/fers/fer-types.json must not
    fail every model that sets a ferType -- the rule is skipped instead
    (silently, per-question), with a single warning logged regardless of how
    many `validate_content` calls hit the empty taxonomy."""
    import logging

    import fipm.km_content as km_content

    empty_settings = Settings(data_dir=str(tmp_path))
    monkeypatch.setattr(km_content, "_fer_type_warning_logged", False)

    doc = _base_doc()
    doc["sections"][0]["questions"][0]["ferType"] = "identifier-service"

    with caplog.at_level(logging.WARNING, logger="fipm.km_content"):
        errors1 = km_content.validate_content(doc, settings=empty_settings)
        errors2 = km_content.validate_content(doc, settings=empty_settings)

    assert _find(errors1, "sections[0].questions[0].ferType", "unknown_fer_type") is None
    assert _find(errors2, "sections[0].questions[0].ferType", "unknown_fer_type") is None
    fer_taxonomy_warnings = [r for r in caplog.records if "FER type taxonomy" in r.message]
    assert len(fer_taxonomy_warnings) == 1


def test_validation_stops_early_once_max_errors_reached(monkeypatch, settings):
    """Review finding 14: an oversized document must not make
    `validate_content` do unbounded work -- once MAX_ERRORS errors have
    accumulated, it stops visiting further sections instead of building an
    ever-larger error list that gets truncated only at the very end."""
    import fipm.km_content as km_content

    call_count = 0
    original_check_langmap = km_content._check_langmap

    def counting_check_langmap(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_check_langmap(*args, **kwargs)

    monkeypatch.setattr(km_content, "_check_langmap", counting_check_langmap)

    # Each of 10,000 sections is missing both its `id` and its `title`, so
    # every section that actually gets processed contributes two errors.
    doc = {
        "title": {"en": "T"},
        "description": {"en": "D"},
        "sections": [{"questions": []} for _ in range(10_000)],
    }
    errors = km_content.validate_content(doc, settings=settings)
    assert len(errors) == km_content.MAX_ERRORS
    # Without the early exit this would be ~10,000 (one call per section);
    # MAX_ERRORS=50 errors at 2 per section is reached after ~25 sections.
    assert call_count < 100, call_count


def test_publishing_requires_a_visible_question(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["hidden"] = True
    errors_draft = validate_content(doc, settings=settings)
    assert _find(errors_draft, "sections", "no_visible_questions") is None

    errors_publish = validate_content(doc, publishing=True, settings=settings)
    assert _find(errors_publish, "sections", "no_visible_questions") is not None


def test_validate_content_does_not_mutate_input(settings):
    doc = _base_doc()
    before = copy.deepcopy(doc)
    validate_content(doc, settings=settings)
    assert doc == before


@pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)
def test_real_gofair_model_validates_clean():
    real_settings = Settings(data_dir=str(REAL_DATA_DIR))
    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))
    assert validate_content(doc, settings=real_settings) == []


@pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)
def test_import_data_reports_all_skipped_on_warm_db_with_real_data(tmp_path):
    db_path = str(tmp_path / "warm.db")
    env = os.environ.copy()
    env["FIPM_DB_PATH"] = db_path
    env["FIPM_DATA_DIR"] = str(REAL_DATA_DIR)
    env["FIPM_STATIC_DIR"] = str(tmp_path / "no-such-static-dir")
    env.pop("FIPM_ADMIN_EMAIL", None)
    env.pop("FIPM_ADMIN_PASSWORD", None)

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "fipm", "import-data"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    first = _run()
    assert first.returncode == 0, first.stdout + first.stderr

    second = _run()
    assert second.returncode == 0, second.stdout + second.stderr
    for line in second.stdout.splitlines():
        if line.startswith("knowledge_models:"):
            assert "created=0 updated=0" in line, line
