"""spec 02-core-flows.md §8 item 7: a full participant round trip against the
real 21-question questionnaire -- create a session, POST /api/fips with
sessionId + joinCode, then 21 sequential PATCHes (one per question, answers
accumulated cumulatively as the frontend editor does per §2.3: each PATCH
replaces `answers` wholesale with everything answered so far), each carrying
the edit token; the final GET has 21 answer entries and export.csv has 22
lines (header + 21).

Uses the real data/knowledge-models/gofair-fip-mini-1.0.0.json (same pattern
as test_real_data_smoke.py) since the tests/fixtures/ test-km fixture only
has 2 questions. Skips cleanly if the real data/ directory isn't present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm.config import Settings
from fipm.importer import ImportSummary, import_knowledge_model_doc

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"

pytestmark = pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)


def test_21_sequential_patches_then_csv_has_22_lines(client, client_factory, db_session, settings):
    real_settings = Settings(
        data_dir=str(REAL_DATA_DIR), db_path=settings.db_path, base_url=settings.base_url
    )
    # Import only the real gofair-fip-mini model, not every file under
    # data/knowledge-models/ (which now also holds CONFOA 2026 draft forks
    # whose promoted inlineFers would otherwise leak into the shared
    # session DB -- see test_rdf_export.py's real_km_loaded).
    summary = ImportSummary()
    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))
    import_knowledge_model_doc(db_session, real_settings, summary, doc, force=False)
    assert summary.knowledge_models.created + summary.knowledge_models.skipped >= 1

    question_ids = [q["id"] for section in doc["sections"] for q in section["questions"]]
    assert len(question_ids) == 21

    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "roundtrip-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "round trip session",
            "questionnaireRef": {"id": doc["id"], "version": doc["version"]},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": doc["id"], "version": doc["version"]},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "community": {"name": "Round trip group"},
        },
    )
    assert created.status_code == 201
    fip = created.json()
    fip_id = fip["id"]
    edit_token = fip["editToken"]
    assert fip["answers"] == []

    accumulated: list[dict] = []
    for qid in question_ids:
        accumulated.append(
            {
                "questionId": qid,
                "declarations": [{"ferFreeText": f"resource for {qid}", "status": "current"}],
            }
        )
        r = participant.patch(
            f"/api/fips/{fip_id}",
            json={"answers": accumulated},
            headers={"X-Edit-Token": edit_token},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["answers"]) == len(accumulated)

    final = participant.get(f"/api/fips/{fip_id}")
    assert final.status_code == 200
    assert len(final.json()["answers"]) == 21

    export = participant.get(f"/api/fips/{fip_id}/export.csv")
    assert export.status_code == 200
    raw = export.content.decode("utf-8-sig")
    lines = raw.split("\r\n")
    data_lines = [line for line in lines[1:] if line]
    assert len(lines) >= 22
    assert len(data_lines) == 21
