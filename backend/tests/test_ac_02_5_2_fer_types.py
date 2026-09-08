"""spec 02-core-flows.md §5.2 / §8 item 2: GET /api/fer-types, backed by
fipm.fer_types.get_fer_types() and data/fers/fer-types.json. Public, no auth."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_FER_TYPES_PATH = REPO_ROOT / "data" / "fers" / "fer-types.json"


def test_fer_types_total_and_keys_in_file_order(raw_client):
    # spec 00 §3's 12 keys, in file order; no cookie, no Origin header needed
    # (raw_client sends neither) since the route is a plain GET.
    r = raw_client.get("/api/fer-types")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 12
    assert len(body["items"]) == 12

    expected_keys = [
        "identifier-service",
        "metadata-schema",
        "metadata-data-linking-schema",
        "registry",
        "communication-protocol",
        "authentication-authorization-service",
        "metadata-preservation-policy",
        "knowledge-representation-language",
        "structured-vocabulary",
        "semantic-model",
        "data-usage-license",
        "provenance-model",
    ]
    assert [item["key"] for item in body["items"]] == expected_keys
    for item in body["items"]:
        assert item["iri"]
        assert item["principle"]
        assert "en" in item["label"]

    assert r.headers["cache-control"] == "public, max-age=3600"


def test_fer_types_match_real_data_file_when_present():
    if not REAL_FER_TYPES_PATH.is_file():
        return
    doc = json.loads(REAL_FER_TYPES_PATH.read_text(encoding="utf-8"))
    assert len(doc["types"]) == 12
