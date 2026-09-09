"""AC1/AC2 (spec 06-dmp-linkage.md §5): `relatedDmps` normalisation on
PATCH /api/fips/{id} -- FioDMP URL detection/canonicalisation, generic
"other" URLs, and the four 422 validation codes."""

from __future__ import annotations

import itertools

_EMAILS = (f"dmp-ac1-user-{i}@example.com" for i in itertools.count())


def _create_fip(client) -> str:
    client.post(
        "/api/auth/register",
        json={
            "email": next(_EMAILS),
            "password": "correcthorsebattery",
            "displayName": "DMP",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "answers": []},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_fiodmp_url_normalised_and_generic_url_kept_as_other(client):
    fip_id = _create_fip(client)

    patched = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [
                {
                    "url": "https://www.fiodmp.fiocruz.br/publico/kqu5n0c/",
                    "version": "13",
                    "system": "x",
                },
                {"url": "https://example.org/plan?x=1#f"},
            ]
        },
    )
    assert patched.status_code == 200, patched.text
    entries = patched.json()["relatedDmps"]
    assert entries[0] == {
        "url": "https://fiodmp.fiocruz.br/KQU5N0C",
        "version": "13",
        "system": "FioDMP",
        "dmpId": "KQU5N0C",
    }
    assert entries[1] == {
        "url": "https://example.org/plan?x=1",
        "version": None,
        "system": "other",
    }
    assert "dmpId" not in entries[1]

    fetched = client.get(f"/api/fips/{fip_id}").json()
    assert fetched["relatedDmps"] == entries


def test_http_scheme_rejected(client):
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}", json={"relatedDmps": [{"url": "http://example.org/plan"}]}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_invalid"


def test_javascript_scheme_rejected(client):
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}", json={"relatedDmps": [{"url": "javascript:alert(1)"}]}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_invalid"


def test_eleven_entries_rejected(client):
    fip_id = _create_fip(client)
    entries = [{"url": f"https://example.org/plan-{i}"} for i in range(11)]
    resp = client.patch(f"/api/fips/{fip_id}", json={"relatedDmps": entries})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_too_many"


def test_same_plan_twice_in_different_casings_rejected(client):
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [
                {"url": "https://fiodmp.fiocruz.br/kqu5n0c"},
                {"url": "https://fiodmp.fiocruz.br/KQU5N0C"},
            ]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_duplicate"


def test_thirty_char_version_rejected(client):
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={"relatedDmps": [{"url": "https://example.org/plan", "version": "x" * 30}]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_version_invalid"


def test_surrounding_whitespace_stripped_and_accepted(client):
    """Review finding 6: a pasted URL with leading/trailing whitespace is
    accepted (and normalised), not rejected -- only an *internal* control/
    whitespace character still 422s."""
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={"relatedDmps": [{"url": "  https://example.org/plan  "}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["relatedDmps"][0]["url"] == "https://example.org/plan"


def test_internal_whitespace_still_rejected(client):
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={"relatedDmps": [{"url": "https://exa mple.org/plan"}]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_invalid"


def test_genuine_idn_host_encoded_to_punycode(client):
    """Review finding 7: a legitimate non-ASCII hostname still round-trips
    through `str.encode("idna")` to its canonical punycode form."""
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}", json={"relatedDmps": [{"url": "https://münchen.de/plan"}]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["relatedDmps"][0]["url"] == "https://xn--mnchen-3ya.de/plan"


def test_fullwidth_host_rejected(client):
    """`str.encode("idna")` would silently fold this fullwidth host onto
    plain ASCII "example.com" instead of erroring -- reject it instead."""
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={"relatedDmps": [{"url": "https://ｅｘａｍｐｌｅ.com/"}]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_invalid"


def test_zero_width_character_in_host_rejected(client):
    """`str.encode("idna")` would silently strip a zero-width space out of
    the host instead of erroring -- reject it instead."""
    fip_id = _create_fip(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={"relatedDmps": [{"url": "https://exa​mple.org/plan"}]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_url_invalid"


def test_post_fips_also_normalises(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "dmp-ac1-create@example.com",
            "password": "correcthorsebattery",
            "displayName": "DMP",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [],
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/publico/AbCd1234"}],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["relatedDmps"] == [
        {
            "url": "https://fiodmp.fiocruz.br/ABCD1234",
            "version": None,
            "system": "FioDMP",
            "dmpId": "ABCD1234",
        }
    ]
