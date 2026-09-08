"""Review findings 2, 4, 6 (routers/knowledge_models.py `import_knowledge_model`):
a request body that isn't valid JSON (including one that overflows the
decoder's recursion limit) is 400 `invalid_json`, not a 500; a document whose
`title`/`description`/`sections`/`changelog` are the wrong JSON type is 400
`invalid_content` (previously silently coerced to an empty default and
accepted as 201); `attribution` and `forkedFrom` on the imported document are
carried into the new draft's content, so re-importing an exported fork keeps
its CC-BY-SA attribution and lineage."""

from __future__ import annotations


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _base_document() -> dict:
    return {
        "id": "ignored-client-id",
        "version": "9.9.9",
        "status": "published",
        "license": "CC0-1.0",
        "source": "Test",
        "title": {"en": "Import test"},
        "description": {"en": "Import test description"},
        "changelog": [],
        "sections": [],
    }


def test_malformed_json_body_is_400_invalid_json(client):
    _register(client, "import-malformed-json@example.com")
    r = client.post(
        "/api/knowledge-models/import",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_json"


def test_deeply_nested_json_body_is_400_invalid_json_not_500(client):
    """The stdlib json decoder raises RecursionError (not ValueError) on
    input nested past sys.getrecursionlimit(); the import route must still
    answer 400, not crash with an unhandled 500."""
    _register(client, "import-deep-recursion@example.com")
    nested = "[" * 10000 + "]" * 10000
    r = client.post(
        "/api/knowledge-models/import",
        content=('{"document": ' + nested + "}").encode(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_json"


def test_wrong_typed_title_is_invalid_content_not_an_empty_model(client):
    _register(client, "import-bad-title-type@example.com")
    doc = _base_document()
    doc["title"] = "not an object"
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_content"


def test_wrong_typed_sections_is_invalid_content_not_an_empty_model(client):
    _register(client, "import-bad-sections-type@example.com")
    doc = _base_document()
    doc["sections"] = "not a list"
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_content"


def test_wrong_typed_description_is_invalid_content(client):
    _register(client, "import-bad-description-type@example.com")
    doc = _base_document()
    doc["description"] = ["not", "an", "object"]
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_content"


def test_wrong_typed_changelog_is_invalid_content(client):
    _register(client, "import-bad-changelog-type@example.com")
    doc = _base_document()
    doc["changelog"] = "not a list"
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["detail"] == "invalid_content"
    assert any(e["path"] == "changelog" for e in body["errors"])


def test_attribution_and_forked_from_round_trip_through_import(client):
    _register(client, "import-attribution-roundtrip@example.com")
    doc = _base_document()
    doc["attribution"] = "FIP mini-questionnaire v2.0.0 (c) Example, CC BY-SA 4.0."
    doc["forkedFrom"] = {"id": "gofair-fip-mini", "version": "1.0.0"}
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 201, r.text
    content = r.json()["content"]
    assert content["attribution"] == doc["attribution"]
    assert content["forkedFrom"] == doc["forkedFrom"]
