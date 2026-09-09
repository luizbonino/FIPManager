"""AC3 (spec 06-dmp-linkage.md §5): `dmpEvidence` round-trips through
PATCH/GET, an out-of-range `dmpIndex` is rejected, dropping `relatedDmps`
out from under a still-cited evidence object is rejected, and an all-empty
evidence object is stored as `null`."""

from __future__ import annotations

import itertools

_EMAILS = (f"dmp-ac2-user-{i}@example.com" for i in itertools.count())


def _create_fip_with_answer(client):
    client.post(
        "/api/auth/register",
        json={"email": next(_EMAILS), "password": "correcthorsebattery", "displayName": "DMP"},
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_evidence_round_trips_through_patch_and_get(client):
    fip_id = _create_fip_with_answer(client)

    patched = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C", "version": "13"}],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "dmpEvidence": {"dmpIndex": 0, "section": "C", "questionRef": "C.3"},
                        }
                    ],
                }
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    decl = patched.json()["answers"][0]["declarations"][0]
    assert decl["dmpEvidence"] == {"dmpIndex": 0, "section": "C", "questionRef": "C.3"}

    fetched = client.get(f"/api/fips/{fip_id}").json()
    assert fetched["answers"][0]["declarations"][0]["dmpEvidence"] == {
        "dmpIndex": 0,
        "section": "C",
        "questionRef": "C.3",
    }


def test_index_out_of_range_rejected(client):
    fip_id = _create_fip_with_answer(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C"}],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "dmpEvidence": {"dmpIndex": 1},
                        }
                    ],
                }
            ],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_evidence_index_invalid"


def test_dropping_related_dmps_while_evidence_stands_rejected(client):
    fip_id = _create_fip_with_answer(client)
    setup = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C"}],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "dmpEvidence": {"dmpIndex": 0, "questionRef": "C.3"},
                        }
                    ],
                }
            ],
        },
    )
    assert setup.status_code == 200, setup.text

    # This PATCH only touches relatedDmps; the untouched, already-stored
    # declaration still cites index 0.
    resp = client.patch(f"/api/fips/{fip_id}", json={"relatedDmps": []})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dmp_evidence_without_dmp"


def test_all_empty_evidence_stored_as_null(client):
    fip_id = _create_fip_with_answer(client)
    resp = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "dmpEvidence": {"dmpIndex": None, "section": None, "questionRef": None},
                        }
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["answers"][0]["declarations"][0]["dmpEvidence"] is None
