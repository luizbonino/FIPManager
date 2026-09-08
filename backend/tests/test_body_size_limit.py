"""Review finding 3 (fipm.main.BodySizeLimitMiddleware): a POST/PUT/PATCH
under /api/ whose Content-Length already exceeds `settings.max_body_bytes` is
rejected with 413 `payload_too_large` before the body is read; a chunked
body with no Content-Length is rejected the moment the running total crosses
the cap. A GET is never limited (it has no body to bound)."""

from __future__ import annotations

import pytest


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def small_cap(monkeypatch):
    """A tight FIPM_MAX_BODY_BYTES for this test module: fipm.config.get_settings()
    is process-wide lru_cache'd, so the app-level middleware (built once at
    import time in fipm.main) keeps whatever cap was in effect when the app
    module was first imported. These tests instead exercise the
    import-specific fallback cap (finding 3's "keep the import-specific
    check as a fallback"), which reads settings fresh on every request."""
    from fipm.config import get_settings

    monkeypatch.setenv("FIPM_MAX_BODY_BYTES", "1000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_import_fallback_rejects_oversized_content_length(client, small_cap):
    _register(client, "bodylimit-fallback@example.com")
    big_doc = {"title": {"en": "x" * 5000}, "sections": []}
    r = client.post("/api/knowledge-models/import", json={"document": big_doc})
    assert r.status_code == 413, r.text
    assert r.json()["detail"] == "payload_too_large"


def test_get_request_is_never_size_limited(client):
    r = client.get("/api/knowledge-models")
    assert r.status_code == 200


def test_app_level_middleware_rejects_declared_content_length_before_reading(client):
    """The app-wide middleware (built once, at import time, from whatever
    FIPM_MAX_BODY_BYTES was set when fipm.main was first imported) is
    exercised directly here with the default 2 MiB cap: a declared
    Content-Length above it is rejected without FastAPI ever attempting to
    parse the body as JSON (a malformed-but-huge body would otherwise 422,
    not 413)."""
    huge_content_length = str(2 * 1024 * 1024 + 1)
    r = client.post(
        "/api/knowledge-models",
        content=b"not even json",
        headers={"content-type": "application/json", "content-length": huge_content_length},
    )
    assert r.status_code == 413, r.text
    assert r.json()["detail"] == "payload_too_large"
