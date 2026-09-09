"""AC9 (spec 06-dmp-linkage.md §5): by default Content-Security-Policy
contains frame-ancestors 'self' https://fiodmp.fiocruz.br and no
X-Frame-Options; with FIPM_EMBED_ALLOWED_ORIGINS="" it contains
frame-ancestors 'self' and X-Frame-Options: SAMEORIGIN; a public FIP gets
Cache-Control: public, max-age=300, a private one private, no-store."""

from __future__ import annotations

import itertools

_EMAILS = (f"dmp-ac9-user-{i}@example.com" for i in itertools.count())


def _create_fip(client, *, visibility: str):
    client.post(
        "/api/auth/register",
        json={
            "email": next(_EMAILS),
            "password": "correcthorsebattery",
            "displayName": "E",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [],
            "visibility": visibility,
            "community": {"name": "Headers group"},
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_default_csp_allows_fiodmp_and_no_x_frame_options(client):
    fip_id = _create_fip(client, visibility="public")
    resp = client.get(f"/fips/{fip_id}/embed")
    assert resp.status_code == 200
    csp = resp.headers["content-security-policy"]
    assert "frame-ancestors 'self' https://fiodmp.fiocruz.br" in csp
    assert "x-frame-options" not in {k.lower() for k in resp.headers.keys()}


def test_empty_allowed_origins_self_only_and_x_frame_options_sameorigin(client, monkeypatch):
    from fipm.config import get_settings

    fip_id = _create_fip(client, visibility="public")

    monkeypatch.setenv("FIPM_EMBED_ALLOWED_ORIGINS", "")
    get_settings.cache_clear()
    try:
        resp = client.get(f"/fips/{fip_id}/embed")
        assert resp.status_code == 200
        csp = resp.headers["content-security-policy"]
        assert "frame-ancestors 'self'" in csp
        assert "fiodmp" not in csp
        assert resp.headers["x-frame-options"] == "SAMEORIGIN"
    finally:
        get_settings.cache_clear()


def test_public_fip_cache_control_public_max_age(client):
    fip_id = _create_fip(client, visibility="public")
    resp = client.get(f"/fips/{fip_id}/embed")
    assert resp.headers["cache-control"] == "public, max-age=300"


def test_private_fip_cache_control_no_store(client):
    fip_id = _create_fip(client, visibility="private")
    resp = client.get(f"/fips/{fip_id}/embed")
    assert resp.status_code == 200  # owner's own cookie
    assert resp.headers["cache-control"] == "private, no-store"
