"""AC8 (spec 06-dmp-linkage.md §5): embed content -- 21 question rows in
knowledge-model order, the n / 21 count matching the stored answers, the
questionnaire id and version, the linked plan's URL, an href of
{base_url}/fips/{id}, the CC BY-SA questionnaire credit (KM licence
CC-BY-SA-4.0), and ?lang=pt-BR switching the fixed labels while ?lang=zz
falls back to the FIP's language.

Uses the real gofair-fip-mini-1.0.0 knowledge model (21 questions,
CC-BY-SA-4.0), like test_rdf_export.py; skips cleanly if data/ isn't
present.
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


@pytest.fixture()
def question_ids():
    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))
    return [q["id"] for section in doc["sections"] for q in section["questions"]]


def test_embed_content(client, real_km_loaded, question_ids):
    assert len(question_ids) == 21

    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac8-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    answers = [
        {"questionId": qid, "declarations": [{"ferFreeText": "n/a", "status": "current"}]}
        for qid in question_ids[:5]
    ]
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "answers": answers,
            "visibility": "public",
            "community": {"name": "AC8 group"},
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C", "version": "13"}],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    resp = client.get(f"/fips/{fip_id}/embed")
    assert resp.status_code == 200
    body = resp.text

    # 21 question rows, in knowledge-model order.
    positions = [body.index(f">{qid}<") for qid in question_ids]
    assert positions == sorted(positions)

    # n / 21 answered count.
    assert "5 / 21" in body

    # questionnaire id and version.
    assert KM_ID in body
    assert KM_VERSION in body

    # the linked plan's URL.
    assert "https://fiodmp.fiocruz.br/KQU5N0C" in body

    # href of {base_url}/fips/{id}.
    assert f'href="{real_km_loaded.base_url}/fips/{fip_id}"' in body

    # CC BY-SA questionnaire credit (KM licence CC-BY-SA-4.0).
    assert "GO FAIR Foundation" in body
    assert "CC BY-SA 4.0" in body


def test_lang_query_param_switches_fixed_labels_and_falls_back(client, real_km_loaded):
    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac8-lang@example.com",
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": KM_ID, "version": KM_VERSION},
            "answers": [],
            "visibility": "public",
            "language": "pt-PT",
            "community": {"name": "AC8 lang group"},
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    pt_br = client.get(f"/fips/{fip_id}/embed", params={"lang": "pt-BR"})
    assert pt_br.status_code == 200
    assert 'lang="pt-BR"' in pt_br.text
    assert "Ver o FIP completo" in pt_br.text

    # ?lang=zz isn't one of the three -> falls back to the FIP's own
    # language (pt-PT here), not to en.
    fallback = client.get(f"/fips/{fip_id}/embed", params={"lang": "zz"})
    assert fallback.status_code == 200
    assert 'lang="pt-PT"' in fallback.text
