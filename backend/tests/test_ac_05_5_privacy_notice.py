"""AC5 (spec 05-v1-completion.md §8): GET /api/privacy?lang=pt-PT and
?lang=es return that language's markdown, ?lang=de and no lang return en,
and every response carries the same notice version.

Assumption (see fipm/privacy.py docstring): the spec describes a shared
data/i18n/privacy/version.json, but the actual data/i18n/privacy/*.md files
instead each start with an identical `<!-- version: ... -->` header comment
and no version.json exists on disk; this test therefore checks that
`version` is non-empty and identical across languages, rather than reading a
version.json that isn't there.

Review finding 11: the test fixtures' header comment is `test-v1` (matching
`PRIVACY_VERSION` used across the rest of the suite when registering) --
deliberately *not* a date, unlike the real data/i18n/privacy/*.md files. So
`date` must come back empty here, not a duplicate of `version`; see
test_privacy_notice_date_helper below for the case where the header value
actually does parse as YYYY-MM-DD."""

from __future__ import annotations

from fipm.privacy import privacy_notice_date


def test_privacy_notice_date_helper():
    assert privacy_notice_date("2026-09-12") == "2026-09-12"
    assert privacy_notice_date("test-v1") == ""
    assert privacy_notice_date("unknown") == ""
    assert privacy_notice_date("1.0") == ""


def test_privacy_lang_resolution_and_shared_version(client):
    en = client.get("/api/privacy")
    assert en.status_code == 200
    en_body = en.json()
    assert en_body["lang"] == "en"
    assert "Privacy notice (en)" in en_body["markdown"]
    assert en_body["version"] == "test-v1"
    # The fixture header isn't a real date, so `date` must not just echo
    # `version` back (review finding 11) -- it's the ISO date or nothing.
    assert en_body["date"] == ""

    pt_pt = client.get("/api/privacy", params={"lang": "pt-PT"})
    assert pt_pt.status_code == 200
    pt_pt_body = pt_pt.json()
    assert pt_pt_body["lang"] == "pt-PT"
    assert "pt-PT" in pt_pt_body["markdown"]
    assert pt_pt_body["version"] == en_body["version"]

    es = client.get("/api/privacy", params={"lang": "es"})
    assert es.status_code == 200
    es_body = es.json()
    assert es_body["lang"] == "es"
    assert "privacidad (es)" in es_body["markdown"]
    assert es_body["version"] == en_body["version"]

    unknown = client.get("/api/privacy", params={"lang": "de"})
    assert unknown.status_code == 200
    assert unknown.json()["lang"] == "en"
    assert unknown.json()["markdown"] == en_body["markdown"]

    no_lang = client.get("/api/privacy")
    assert no_lang.json()["lang"] == "en"


def test_privacy_response_carries_cache_control_and_substitutes_placeholders(client):
    r = client.get("/api/privacy")
    assert r.status_code == 200
    assert "max-age=3600" in r.headers.get("cache-control", "")
    assert "{{CONTACT_EMAIL}}" not in r.json()["markdown"]
    assert "{{HOSTING_ORG}}" not in r.json()["markdown"]
