"""GET /api/guides, /api/guides/{guide_id}, /api/guides/images/{filename}:
offline user guides served from docs/ (spec: workshop offline-hotspot
contingency). Mirrors test_ac_05_5_privacy_notice.py's structure.

No fixtures are used here -- docs/ (the real repo content, via the default
FIPM_GUIDES_DIR) is the single source of truth per the task brief, so these
tests exercise the actual shipped guide files rather than test doubles."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from fipm.config import get_settings
from fipm.guides import resolve_guide_image

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


def test_guides_list(client):
    r = client.get("/api/guides")
    assert r.status_code == 200
    body = r.json()
    ids = {item["id"]: item["languages"] for item in body["items"]}
    assert set(ids) == {"participant", "administrator"}
    for langs in ids.values():
        assert "en" in langs
        assert "pt-PT" in langs
        assert "pt-BR" in langs
        assert "es" in langs


@pytest.mark.parametrize("guide_id", ["participant", "administrator"])
@pytest.mark.parametrize("lang", ["en", "pt-PT", "pt-BR", "es"])
def test_guide_fetch_each_language(client, guide_id, lang):
    r = client.get(f"/api/guides/{guide_id}", params={"lang": lang})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == guide_id
    assert body["language"] == lang
    assert len(body["markdown"]) > 0


def test_guide_fetch_no_lang_defaults_to_en(client):
    r = client.get("/api/guides/participant")
    assert r.status_code == 200
    assert r.json()["language"] == "en"


def test_guide_fallback_pt_pt_to_pt_br(client, tmp_path, monkeypatch):
    """When a guide has pt-BR but not pt-PT, ?lang=pt-PT must fall back to
    pt-BR (not straight to en). Built from a temp guides_dir with only en +
    pt-BR present, since every real guide already has pt-PT."""
    (tmp_path / "participant-guide.md").write_text("# EN\n", encoding="utf-8")
    (tmp_path / "participant-guide.pt-BR.md").write_text("# PT-BR\n", encoding="utf-8")

    from fipm import guides as guides_module

    guides_module._load.cache_clear()
    monkeypatch.setattr(get_settings(), "guides_dir", str(tmp_path))
    try:
        from starlette.testclient import TestClient

        from fipm.main import app

        with TestClient(app, headers={"origin": get_settings().base_url}) as c:
            r = c.get("/api/guides/participant", params={"lang": "pt-PT"})
            assert r.status_code == 200
            body = r.json()
            assert body["language"] == "pt-BR"
            assert "PT-BR" in body["markdown"]
    finally:
        guides_module._load.cache_clear()


def test_guide_image_rewrite_skips_fenced_code_blocks(tmp_path, monkeypatch):
    """`](images/...)` written verbatim inside a fenced code block (e.g. a
    snippet of guide markdown source quoted for the reader) must not be
    rewritten -- only real image references outside a fence are (review
    finding 6)."""
    (tmp_path / "participant-guide.md").write_text(
        "# EN\n\n```\n![alt](images/foo.png)\n```\n\n![Real image](images/bar.png)\n",
        encoding="utf-8",
    )

    from fipm import guides as guides_module

    guides_module._load.cache_clear()
    monkeypatch.setattr(get_settings(), "guides_dir", str(tmp_path))
    try:
        from starlette.testclient import TestClient

        from fipm.main import app

        with TestClient(app, headers={"origin": get_settings().base_url}) as c:
            r = c.get("/api/guides/participant")
            assert r.status_code == 200
            markdown = r.json()["markdown"]
            assert "```\n![alt](images/foo.png)\n```" in markdown
            assert "![Real image](/api/guides/images/bar.png)" in markdown
    finally:
        guides_module._load.cache_clear()


def test_guide_image_rewrite_only_applies_to_image_links(tmp_path, monkeypatch):
    """A plain (non-image) link pointing into images/ must not be rewritten
    to the images endpoint -- that endpoint only ever serves `.png` files,
    so rewriting `[readme](images/README.md)` would just produce a dead
    link (review finding 6)."""
    (tmp_path / "participant-guide.md").write_text(
        "# EN\n\n[readme](images/README.md) and ![alt](images/foo.png)\n",
        encoding="utf-8",
    )

    from fipm import guides as guides_module

    guides_module._load.cache_clear()
    monkeypatch.setattr(get_settings(), "guides_dir", str(tmp_path))
    try:
        from starlette.testclient import TestClient

        from fipm.main import app

        with TestClient(app, headers={"origin": get_settings().base_url}) as c:
            r = c.get("/api/guides/participant")
            assert r.status_code == 200
            markdown = r.json()["markdown"]
            assert "[readme](images/README.md)" in markdown
            assert "![alt](/api/guides/images/foo.png)" in markdown
    finally:
        guides_module._load.cache_clear()


def test_guide_unknown_lang_falls_back_to_en(client):
    en = client.get("/api/guides/participant", params={"lang": "en"})
    unknown = client.get("/api/guides/participant", params={"lang": "de"})
    assert unknown.status_code == 200
    assert unknown.json()["language"] == "en"
    assert unknown.json()["markdown"] == en.json()["markdown"]


def test_guide_unknown_guide_id_is_404(client):
    r = client.get("/api/guides/nonexistent")
    assert r.status_code == 404


def test_guide_image_link_rewritten(client):
    r = client.get("/api/guides/participant")
    assert r.status_code == 200
    markdown = r.json()["markdown"]
    assert "](images/" not in markdown
    assert "](/api/guides/images/" in markdown


def test_guide_anchor_not_rewritten(client):
    r = client.get("/api/guides/administrator")
    assert r.status_code == 200
    markdown = r.json()["markdown"]
    assert "](#1-the-pieces-and-how-they-fit)" in markdown


def test_guide_cross_doc_link_rewritten_to_in_app_route(client):
    """A link from the administrator guide to the participant guide is
    mapped onto the in-app /guide route rather than left as a relative
    .md link -- safeHref's allowlist would otherwise reject it and render
    a dead `href="#"` (review finding 4)."""
    r = client.get("/api/guides/administrator")
    assert r.status_code == 200
    markdown = r.json()["markdown"]
    assert "](participant-guide.md)" not in markdown
    assert "](/guide)" in markdown


def test_guide_workshop_link_rendered_as_plain_text(client):
    """Links into workshop/ (the facilitator script, the participant
    handout) point at documents not served in-app at all, so the link
    markup is stripped and only the label text remains (review finding 4)."""
    r = client.get("/api/guides/administrator")
    assert r.status_code == 200
    markdown = r.json()["markdown"]
    assert "](workshop/facilitator-script.md)" not in markdown
    assert "workshop/facilitator-script.md" in markdown


def test_guide_image_serving(client):
    # home-join-code.png is a real image referenced by the participant guide.
    r2 = client.get("/api/guides/images/home-join-code.png")
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "image/png"
    assert "max-age" in r2.headers.get("cache-control", "")
    assert r2.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize(
    "filename",
    [
        "..%2fetc%2fpasswd",
        "home-join-code.txt",
        "home-join-code.svg",
        "..png",
        "a/b.png",
    ],
)
def test_guide_image_path_traversal_refused(client, filename):
    r = client.get(f"/api/guides/images/{filename}")
    assert r.status_code in (404, 400, 422)
    assert r.status_code != 200


def test_guide_image_dotdot_traversal_refused(client):
    """`../../../etc/passwd` collapses via URL dot-segment normalization
    before it ever reaches our route (httpx/starlette resolve `..` in the
    path), so the request never actually hits `resolve_guide_image` here --
    it falls through to the SPA catch-all instead. What matters is that no
    file content leaks and nothing is served as an image; the *actual*
    traversal defense (filename whitelist + resolved-path containment
    check) is exercised directly below and in the router regardless of how
    a path reaches it."""
    r = client.get("/api/guides/images/../../../etc/passwd")
    assert "image/png" not in r.headers.get("content-type", "")
    assert "root:" not in r.text


def test_guide_image_unknown_filename_404(client):
    r = client.get("/api/guides/images/does-not-exist.png")
    assert r.status_code == 404


def test_resolve_guide_image_rejects_traversal_directly():
    settings = get_settings()
    for bad in ("../../../etc/passwd", "/etc/passwd", "a/b.png", "x.txt", "x.png\x00y"):
        with pytest.raises(HTTPException):
            resolve_guide_image(settings, bad)
