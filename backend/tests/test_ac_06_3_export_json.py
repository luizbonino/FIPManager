"""AC4 (spec 06-dmp-linkage.md §5): export.json resolves dmpEvidence to
{dmpIndex, dmpUrl, dmpSystem, dmpVersion, section, questionRef};
POST /api/fips/import round-trips it back into the stored shape; a legacy
{url, questionRef} stored object still exports and imports."""

from __future__ import annotations

import itertools

from fipm.db import SessionLocal
from fipm.models import Fip

_EMAILS = (f"dmp-ac4-user-{i}@example.com" for i in itertools.count())


def _register(client) -> None:
    client.post(
        "/api/auth/register",
        json={"email": next(_EMAILS), "password": "correcthorsebattery", "displayName": "DMP"},
    )


def test_evidence_resolved_in_export_and_round_trips_through_import(client):
    _register(client)
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
    ).json()
    fip_id = created["id"]

    client.patch(
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

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    doc = export.json()
    f1 = next(a for a in doc["answers"] if a["questionId"] == "F1-metadata")
    assert f1["declarations"][0]["dmpEvidence"] == {
        "dmpIndex": 0,
        "dmpUrl": "https://fiodmp.fiocruz.br/KQU5N0C",
        "dmpSystem": "FioDMP",
        "dmpVersion": "13",
        "section": "C",
        "questionRef": "C.3",
    }

    imported = client.post("/api/fips/import", json=doc)
    assert imported.status_code == 201, imported.text
    new_fip = client.get(f"/api/fips/{imported.json()['id']}").json()
    new_f1 = next(a for a in new_fip["answers"] if a["questionId"] == "F1-metadata")
    assert new_f1["declarations"][0]["dmpEvidence"] == {
        "dmpIndex": 0,
        "section": "C",
        "questionRef": "C.3",
    }
    assert new_fip["relatedDmps"] == [
        {
            "url": "https://fiodmp.fiocruz.br/KQU5N0C",
            "version": "13",
            "system": "FioDMP",
            "dmpId": "KQU5N0C",
        }
    ]


def test_legacy_shape_still_exports_and_imports(client):
    """No FIP can carry evidence through the API yet in the legacy
    {url, questionRef} shape (schemas.py only ever *wrote* that shape in
    v1, before dmpEvidence existed at all) -- so this writes it directly to
    the DB, the way a pre-existing row would carry it."""
    _register(client)
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
            "relatedDmps": [{"url": "https://fiodmp.fiocruz.br/KQU5N0C"}],
        },
    ).json()
    fip_id = created["id"]

    with SessionLocal() as db:
        fip = db.get(Fip, fip_id)
        fip.answers = [
            {
                "questionId": "F1-metadata",
                "declarations": [
                    {
                        "ferId": "https://w3id.org/np/doi",
                        "status": "current",
                        "dmpEvidence": {
                            "url": "https://fiodmp.fiocruz.br/KQU5N0C",
                            "questionRef": "C.3",
                        },
                    }
                ],
                "comment": None,
            }
        ]
        db.commit()

    export = client.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    doc = export.json()
    f1 = next(a for a in doc["answers"] if a["questionId"] == "F1-metadata")
    assert f1["declarations"][0]["dmpEvidence"] == {
        "dmpIndex": None,
        "dmpUrl": "https://fiodmp.fiocruz.br/KQU5N0C",
        "dmpSystem": None,
        "dmpVersion": None,
        "section": None,
        "questionRef": "C.3",
    }

    imported = client.post("/api/fips/import", json=doc)
    assert imported.status_code == 201, imported.text
    new_fip = client.get(f"/api/fips/{imported.json()['id']}").json()
    new_f1 = next(a for a in new_fip["answers"] if a["questionId"] == "F1-metadata")
    # the URL matched the imported relatedDMPs -> reconstructed with a
    # real dmpIndex (spec 06 §2.4's matching-by-url fallback).
    assert new_f1["declarations"][0]["dmpEvidence"] == {
        "dmpIndex": 0,
        "section": None,
        "questionRef": "C.3",
    }
