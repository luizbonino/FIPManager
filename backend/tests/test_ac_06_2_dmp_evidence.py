"""AC3 (spec 06-dmp-linkage.md §5): `dmpEvidence` round-trips through
PATCH/GET, an out-of-range `dmpIndex` is rejected, dropping `relatedDmps`
out from under a still-cited evidence object leaves it unresolved rather
than rejecting the PATCH (review finding 1), and an all-empty evidence
object is stored as `null`."""

from __future__ import annotations

import itertools

from fipm.db import SessionLocal
from fipm.models import Fip

_EMAILS = (f"dmp-ac2-user-{i}@example.com" for i in itertools.count())


def _create_fip_with_answer(client):
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


def test_dropping_related_dmps_while_evidence_stands_leaves_it_unresolved(client):
    """Review finding 1: a PATCH that omits `answers` no longer re-validates
    the FIP's already-stored evidence -- previously, dropping `relatedDmps`
    out from under an untouched, already-stored declaration's `dmpIndex`
    made this (and every future PATCH, e.g. one that only changes
    `visibility`) fail 422 forever. It now succeeds, the stored `dmpIndex`
    is left as-is (still 0, now unresolvable), and export/RDF degrade it
    gracefully (dmpUrl null, section/questionRef kept -- see
    test_ac_06_3_export_json.py / test_ac_06_5_rdf.py)."""
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
    # declaration still cites index 0, but is no longer re-validated.
    resp = client.patch(f"/api/fips/{fip_id}", json={"relatedDmps": []})
    assert resp.status_code == 200, resp.text
    assert resp.json()["relatedDmps"] == []
    decl = resp.json()["answers"][0]["declarations"][0]
    assert decl["dmpEvidence"] == {"dmpIndex": 0, "section": None, "questionRef": "C.3"}

    # A later PATCH that doesn't touch `answers` either (e.g. just
    # visibility) keeps working -- this is exactly what used to wedge shut.
    later = client.patch(f"/api/fips/{fip_id}", json={"visibility": "link"})
    assert later.status_code == 200, later.text
    assert later.json()["visibility"] == "link"


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


def _store_legacy_evidence(fip_id: str, url: str | None, question_ref: str) -> None:
    """No FIP can carry evidence through the API in the legacy {url,
    questionRef} shape (the DmpEvidence pydantic model only has dmpIndex/
    section/questionRef, so a client-sent `url` is silently dropped before
    it reaches storage) -- so this writes it directly to the DB, the way a
    pre-existing row would carry it (same technique as
    test_ac_06_3_export_json.py)."""
    with SessionLocal() as db:
        fip = db.get(Fip, fip_id)
        fip.answers = [
            {
                "questionId": "F1-metadata",
                "declarations": [
                    {
                        "ferId": "https://w3id.org/np/doi",
                        "status": "current",
                        "dmpEvidence": {"url": url, "section": None, "questionRef": question_ref},
                    }
                ],
                "comment": None,
            }
        ]
        db.commit()


def test_patch_migrates_legacy_evidence_to_matching_dmp_index(client):
    """Review finding 1's normalisation path: any successful PATCH silently
    rewrites a legacy `{url, questionRef}` dmpEvidence to `{dmpIndex, ...}`
    when the url matches a related DMP -- even a PATCH that touches neither
    `answers` nor `relatedDmps`."""
    fip_id = _create_fip_with_answer(client)
    related = client.patch(
        f"/api/fips/{fip_id}",
        json={"relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C"}]},
    )
    assert related.status_code == 200, related.text

    _store_legacy_evidence(fip_id, "https://fiodmp.fiocruz.br/KQU5N0C", "C.3")

    patched = client.patch(f"/api/fips/{fip_id}", json={"visibility": "link"})
    assert patched.status_code == 200, patched.text
    decl = patched.json()["answers"][0]["declarations"][0]
    assert decl["dmpEvidence"] == {"dmpIndex": 0, "section": None, "questionRef": "C.3"}


def test_patch_drops_legacy_evidence_url_with_no_matching_dmp(client):
    """Same normalisation path, but the legacy url matches nothing in
    relatedDmps: the stale url is dropped rather than left around to trip
    `apply_dmp_evidence` (which has no `url` case) on a future PATCH that
    does touch `answers`."""
    fip_id = _create_fip_with_answer(client)
    _store_legacy_evidence(fip_id, "https://fiodmp.fiocruz.br/OTHERID", "C.3")

    patched = client.patch(f"/api/fips/{fip_id}", json={"visibility": "link"})
    assert patched.status_code == 200, patched.text
    decl = patched.json()["answers"][0]["declarations"][0]
    assert decl["dmpEvidence"] == {"section": None, "questionRef": "C.3"}
