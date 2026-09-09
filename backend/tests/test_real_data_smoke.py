"""Extra smoke test (coordinator follow-up): now that data/knowledge-models/
gofair-fip-mini-1.0.0.json and data/fers/fer-types.json exist, exercise the
real 21-question questionnaire end to end (import + CSV export) and confirm
all 12 real FER types load. Skips cleanly if the real data/ isn't present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm.config import Settings
from fipm.importer import ImportSummary, _import_knowledge_models

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"

pytestmark = pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)


def test_real_fer_types_loaded():
    from fipm.fer_types import get_fer_types

    real_settings = Settings(data_dir=str(REAL_DATA_DIR))
    types = get_fer_types(real_settings)
    assert len(types) == 12


def test_real_questionnaire_csv_export_smoke(client, db_session, settings):
    real_settings = Settings(
        data_dir=str(REAL_DATA_DIR), db_path=settings.db_path, base_url=settings.base_url
    )
    summary = ImportSummary()
    _import_knowledge_models(db_session, real_settings, summary, force=False)
    assert summary.knowledge_models.created + summary.knowledge_models.skipped >= 1

    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))
    question_ids = [q["id"] for section in doc["sections"] for q in section["questions"]]
    assert len(question_ids) == 21

    client.post(
        "/api/auth/register",
        json={
            "email": "real-smoke@example.com",
            "password": "correcthorsebattery",
            "displayName": "Smoke",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    answers = [
        {"questionId": qid, "declarations": [{"ferFreeText": "n/a", "status": "current"}]}
        for qid in question_ids
    ]
    created = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": doc["id"], "version": doc["version"]}, "answers": answers},
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    export = client.get(f"/api/fips/{fip_id}/export.csv")
    assert export.status_code == 200
    raw = export.content.decode("utf-8-sig")
    data_lines = [line for line in raw.split("\r\n")[1:] if line]
    assert len(data_lines) == len(question_ids)
