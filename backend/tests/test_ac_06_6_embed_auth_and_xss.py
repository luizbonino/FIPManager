"""AC7 (spec 06-dmp-linkage.md §5): GET /fips/{id}/embed -- 200 text/html
for public and link anonymously, 404 text/html for private anonymously, 200
for its owner's cookie and for a valid X-Edit-Token; the body holds no
`<script` and a community name of `<img src=x onerror=alert(1)>` appears
only escaped."""

from __future__ import annotations

import itertools

_EMAILS = (f"dmp-ac7-user-{i}@example.com" for i in itertools.count())

_XSS_NAME = "<img src=x onerror=alert(1)>"


def _create_fip(client, *, visibility: str, community_name: str = "Embed group"):
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
            "community": {"name": community_name},
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_public_and_link_readable_anonymously(client_factory):
    owner = client_factory()
    for visibility in ("public", "link"):
        fip = _create_fip(owner, visibility=visibility)
        anon = client_factory()
        resp = anon.get(f"/fips/{fip['id']}/embed")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/html")
        assert "<script" not in resp.text


def test_private_404_html_anonymously_but_200_for_owner_and_edit_token(client_factory):
    owner = client_factory()
    fip = _create_fip(owner, visibility="private")
    fip_id = fip["id"]

    anon = client_factory()
    anon_resp = anon.get(f"/fips/{fip_id}/embed")
    assert anon_resp.status_code == 404
    assert anon_resp.headers["content-type"].startswith("text/html")
    # never a JSON body: the response is framed.
    assert not anon_resp.text.lstrip().startswith("{")

    owner_resp = owner.get(f"/fips/{fip_id}/embed")
    assert owner_resp.status_code == 200

    # a private FIP created directly (not via a session) has no edit token,
    # so exercise the token path against a session-scoped anonymous FIP.
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ac7-embed",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()
    participant = client_factory()
    session_fip = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "visibility": "private",
            "answers": [],
        },
    ).json()
    token = session_fip["editToken"]

    anon2 = client_factory()
    no_token = anon2.get(f"/fips/{session_fip['id']}/embed")
    assert no_token.status_code == 404
    with_token = anon2.get(f"/fips/{session_fip['id']}/embed", headers={"X-Edit-Token": token})
    assert with_token.status_code == 200


def test_xss_community_name_escaped_not_raw(client_factory):
    owner = client_factory()
    fip = _create_fip(owner, visibility="public", community_name=_XSS_NAME)
    anon = client_factory()
    resp = anon.get(f"/fips/{fip['id']}/embed")
    assert resp.status_code == 200
    assert "<script" not in resp.text
    assert _XSS_NAME not in resp.text
    assert "&lt;img" in resp.text
