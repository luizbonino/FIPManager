"""Review finding 3: POST /fips/import must run reconstructed answers through
Answer/Declaration validation (not insert the export document's answers
verbatim), validate `fip.visibility` against the enum, reject unknown
questionIds, and turn any KeyError/ValidationError from a malformed document
into a 400 with a `detail` code rather than a 500.

Review finding 5: `fip.language` comes from the same free-form dict and must
likewise be validated against the `Language` literal rather than accepted
verbatim -> 400 invalid_language."""

from __future__ import annotations


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "Importer",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201


def _base_doc(**overrides):
    doc = {
        "exportVersion": 1,
        "fip": {"visibility": "private"},
        "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        "answers": [],
    }
    doc.update(overrides)
    return doc


def test_import_rejects_unknown_question_id(client):
    _register(client, "import-unknown-qid@example.com")
    doc = _base_doc(
        answers=[
            {
                "questionId": "not-a-real-question",
                "declarations": [{"ferFreeText": "x", "status": "current"}],
                "comment": None,
            }
        ]
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown_question_id"


def test_import_rejects_bad_declaration_status(client):
    _register(client, "import-bad-status@example.com")
    doc = _base_doc(
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"ferFreeText": "x", "status": "not-a-status"}],
                "comment": None,
            }
        ]
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_answers"


def test_import_rejects_declaration_missing_fer_xor(client):
    _register(client, "import-missing-fer@example.com")
    doc = _base_doc(
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"status": "current"}],  # neither fer nor ferFreeText
                "comment": None,
            }
        ]
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_answers"


def test_import_rejects_answer_missing_question_id_key(client):
    _register(client, "import-missing-qid-key@example.com")
    doc = _base_doc(answers=[{"declarations": [], "comment": "no questionId key at all"}])
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_answers"


def test_import_rejects_invalid_visibility(client):
    _register(client, "import-bad-visibility@example.com")
    doc = _base_doc(fip={"visibility": "not-a-visibility"})
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_visibility"


def test_import_rejects_invalid_language(client):
    _register(client, "import-bad-language@example.com")
    doc = _base_doc(fip={"visibility": "private", "language": "fr"})
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_language"


def test_import_rejects_malformed_orphaned_answers(client):
    """Audit findings 4/11: a malformed `orphanedAnswers` entry (here, a
    declaration missing the ferId/ferFreeText xor) must be 400
    `invalid_orphaned_answers`, not an unvalidated blob that reaches RDF
    export later and 500s there."""
    _register(client, "import-bad-orphaned@example.com")
    doc = _base_doc(
        exportVersion=2,
        orphanedAnswers=[
            {
                "questionId": "A2",
                "declarations": [{"status": "current"}],  # neither fer nor ferFreeText
                "comment": None,
                "fromVersion": "1.0.0",
                "at": "2024-01-01T00:00:00Z",
            }
        ],
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_orphaned_answers"


def test_import_rejects_orphaned_answer_missing_question_id(client):
    _register(client, "import-orphaned-no-qid@example.com")
    doc = _base_doc(
        exportVersion=2,
        orphanedAnswers=[{"declarations": [], "comment": "no questionId key at all"}],
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_orphaned_answers"


def test_import_accepts_well_formed_orphaned_answers(client):
    _register(client, "import-good-orphaned@example.com")
    doc = _base_doc(
        exportVersion=2,
        orphanedAnswers=[
            {
                "questionId": "A2",
                "questionText": {"en": "An old question"},
                "declarations": [{"ferFreeText": "In-house", "status": "current"}],
                "comment": None,
                "fromVersion": "1.0.0",
                "at": "2024-01-01T00:00:00Z",
            }
        ],
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 201, r.text
    # `orphanedAnswers` isn't on FipOut -- confirm it landed via export.json
    # (build_export_json's "orphanedAnswers" array, spec §6).
    export = client.get(f"/api/fips/{r.json()['id']}/export.json")
    assert export.status_code == 200, export.text
    assert export.json()["orphanedAnswers"][0]["questionId"] == "A2"


def test_import_rejects_malformed_migrated_from(client):
    """Audit finding 4: `fip.migratedFrom` used to be taken verbatim, with
    no shape check, straight from the request body."""
    _register(client, "import-bad-migrated-from@example.com")
    doc = _base_doc(fip={"visibility": "private", "migratedFrom": {"id": "only-id"}})
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_migrated_from"


def test_import_accepts_well_formed_migrated_from(client):
    _register(client, "import-good-migrated-from@example.com")
    doc = _base_doc(
        fip={
            "visibility": "private",
            "migratedFrom": {"id": "test-km", "version": "0.9.0", "at": "2024-01-01T00:00:00Z"},
        }
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 201, r.text
    assert r.json()["migratedFrom"]["id"] == "test-km"


def test_import_accepts_well_formed_document(client):
    _register(client, "import-happy@example.com")
    doc = _base_doc(
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"ferFreeText": "In-house", "status": "current"}],
                "comment": "fine",
            }
        ]
    )
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 201, r.text
    assert r.json()["answers"][0]["questionId"] == "F1-metadata"
