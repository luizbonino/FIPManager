"""AC10 (spec 06-dmp-linkage.md §5): GET /api/fips/{id} returns embedUrl and
a summary whose answeredQuestions/declarations/byStatus (all five statuses,
zeros included) match the fixture and whose totalQuestions is 21 (real KM);
POST /api/fips/{id}/prefill-from-dmp returns 501 with
detail == "fiodmp_api_unavailable" and requires.endpoint ==
"GET /api/plans/{id}", 422 for a non-https dmpUrl, 403 for an anonymous
caller with no edit token."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from fipm.config import DECLARATION_STATUSES, Settings
from fipm.importer import ImportSummary, _import_knowledge_models

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"

KM_ID = "gofair-fip-mini"
KM_VERSION = "1.0.0"


@pytest.fixture()
def real_settings(settings):
    return Settings(
        data_dir=str(REAL_DATA_DIR), db_path=settings.db_path, base_url=settings.base_url
    )


@pytest.fixture()
def real_km_loaded(db_session, real_settings):
    summary = ImportSummary()
    _import_knowledge_models(db_session, real_settings, summary, force=False)
    return real_settings


@pytest.mark.skipif(not REAL_KM_PATH.is_file(), reason="real gofair-fip-mini KM not present")
def test_embed_url_and_summary_on_get(client, real_km_loaded):
    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))
    question_ids = [q["id"] for section in doc["sections"] for q in section["questions"]]
    assert len(question_ids) == 21

    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac10-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    answers = [
        {
            "questionId": question_ids[0],
            "declarations": [{"ferFreeText": "a", "status": "current"}],
        },
        {
            "questionId": question_ids[1],
            "declarations": [
                {"ferFreeText": "b", "status": "planned"},
                {"ferFreeText": "c", "status": "current"},
            ],
        },
        # question_ids[2] intentionally left unanswered.
    ]
    created = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": KM_ID, "version": KM_VERSION}, "answers": answers},
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    fetched = client.get(f"/api/fips/{fip_id}").json()
    assert fetched["embedUrl"] == f"{real_km_loaded.base_url}/fips/{fip_id}/embed"

    summary = fetched["summary"]
    assert summary["answeredQuestions"] == 2
    assert summary["declarations"] == 3
    assert summary["totalQuestions"] == 21
    expected_by_status = dict.fromkeys(DECLARATION_STATUSES, 0)
    expected_by_status["current"] = 2
    expected_by_status["planned"] = 1
    assert summary["byStatus"] == expected_by_status
    assert set(summary["byStatus"].keys()) == set(DECLARATION_STATUSES)


_OWNER_EMAILS = (f"dmp-ac10-owner-{i}@example.com" for i in itertools.count())


def _create_anonymous_session_fip(client, client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": next(_OWNER_EMAILS),
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ac10",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()
    fip = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "answers": [],
        },
    ).json()
    return fip


def test_prefill_returns_501_with_contract_body(client, client_factory):
    fip = _create_anonymous_session_fip(client, client_factory)
    resp = client.post(
        f"/api/fips/{fip['id']}/prefill-from-dmp",
        json={"dmpUrl": "https://fiodmp.fiocruz.br/KQU5N0C"},
        headers={"X-Edit-Token": fip["editToken"]},
    )
    assert resp.status_code == 501
    body = resp.json()
    assert body["detail"] == "fiodmp_api_unavailable"
    assert body["requires"]["endpoint"] == "GET /api/plans/{id}"
    assert body["dmpUrl"] == "https://fiodmp.fiocruz.br/KQU5N0C"
    assert body["system"] == "FioDMP"


def test_prefill_422_for_non_https_url(client, client_factory):
    fip = _create_anonymous_session_fip(client, client_factory)
    resp = client.post(
        f"/api/fips/{fip['id']}/prefill-from-dmp",
        json={"dmpUrl": "http://fiodmp.fiocruz.br/KQU5N0C"},
        headers={"X-Edit-Token": fip["editToken"]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_invalid"


def test_prefill_403_for_anonymous_caller_without_edit_token(client, client_factory):
    fip = _create_anonymous_session_fip(client, client_factory)
    anon = client_factory()
    resp = anon.post(
        f"/api/fips/{fip['id']}/prefill-from-dmp",
        json={"dmpUrl": "https://fiodmp.fiocruz.br/KQU5N0C"},
    )
    assert resp.status_code == 403
