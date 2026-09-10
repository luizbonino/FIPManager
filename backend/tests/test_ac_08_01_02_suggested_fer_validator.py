"""spec 08-workshop-picklists.md §6 AC1/AC2: `validate_content` rules 9-13
(suggestedFerIds / allowFreeText / inlineFers / defaultDeclarationStatus /
compactDeclarations / no_answer_path). Pure unit tests against
`km_content.validate_content`, mirroring `test_km_content_validate.py`'s
style."""

from __future__ import annotations

from fipm.km_content import MAX_SUGGESTED_FER_IDS, validate_content


def _base_doc() -> dict:
    return {
        "title": {"en": "Test model"},
        "description": {"en": "A test model"},
        "sections": [
            {
                "id": "sec1",
                "title": {"en": "Section 1"},
                "questions": [
                    {
                        "id": "q1",
                        "principle": "F1",
                        "scope": "metadata",
                        "text": {"en": "Question 1"},
                        "ferType": "identifier-service",
                        "required": False,
                        "allowMultiple": True,
                    }
                ],
            }
        ],
    }


def _find(errors, path, code):
    return next((e for e in errors if e["path"] == path and e["code"] == code), None)


# ---------------------------------------------------------------------------
# AC1
# ---------------------------------------------------------------------------


def test_too_many_suggested_fer_ids_rejected(settings):
    # spec 10-suggested-phrases-and-other.md: cap bumped 12 -> 16 (the 2026-
    # 09-10 CONFOA re-import resolves 15 real FERs on one question).
    doc = _base_doc()
    ids = [f"https://example.org/fer/{i}" for i in range(MAX_SUGGESTED_FER_IDS + 1)]
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = ids
    errors = validate_content(doc, settings=settings, known_fer_ids=set(ids))
    hit = _find(errors, "sections[0].questions[0].suggestedFerIds", "too_many")
    assert hit is not None, errors


def test_duplicate_suggested_fer_id_rejected(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = [
        "https://example.org/fer/a",
        "https://example.org/fer/a",
    ]
    errors = validate_content(doc, settings=settings, known_fer_ids={"https://example.org/fer/a"})
    hit = _find(errors, "sections[0].questions[0].suggestedFerIds[1]", "duplicate_suggested_fer")
    assert hit is not None, errors


def test_non_iri_suggested_fer_id_rejected(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = ["not-a-valid-iri"]
    errors = validate_content(doc, settings=settings, known_fer_ids=set())
    hit = _find(errors, "sections[0].questions[0].suggestedFerIds[0]", "invalid_fer_iri")
    assert hit is not None, errors


def test_unresolved_suggested_fer_id_rejected_with_catalogue_accepted_without(settings):
    """An id absent from both `inlineFers` and `known_fer_ids` is rejected
    when a catalogue snapshot is supplied, and the identical document
    validates clean when `known_fer_ids=None` (rule 10's resolution check
    is skipped entirely, not just its "catalogue half")."""
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = ["https://example.org/fer/unknown"]

    errors_with_catalogue = validate_content(doc, settings=settings, known_fer_ids=set())
    hit = _find(
        errors_with_catalogue,
        "sections[0].questions[0].suggestedFerIds[0]",
        "unknown_suggested_fer",
    )
    assert hit is not None, errors_with_catalogue

    errors_no_catalogue = validate_content(doc, settings=settings, known_fer_ids=None)
    assert errors_no_catalogue == [], errors_no_catalogue


def test_suggested_fer_id_resolves_against_inline_fers_too(settings):
    doc = _base_doc()
    inline_id = "https://fipm.example.org/fers/draft/abc123"
    doc["inlineFers"] = [
        {"id": inline_id, "label": {"en": "Draft FER"}, "type": "identifier-service"}
    ]
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = [inline_id]
    errors = validate_content(doc, settings=settings, known_fer_ids=set())
    assert errors == [], errors


# ---------------------------------------------------------------------------
# AC2
# ---------------------------------------------------------------------------


def test_no_answer_path_only_enforced_when_publishing(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["allowFreeText"] = False
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = []

    errors_draft = validate_content(doc, settings=settings)
    assert _find(errors_draft, "sections[0].questions[0]", "no_answer_path") is None

    errors_publish = validate_content(doc, publishing=True, settings=settings)
    hit = _find(errors_publish, "sections[0].questions[0]", "no_answer_path")
    assert hit is not None, errors_publish


def test_no_answer_path_not_raised_when_suggestions_present(settings):
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["allowFreeText"] = False
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = ["https://example.org/fer/a"]
    errors_publish = validate_content(
        doc, publishing=True, settings=settings, known_fer_ids={"https://example.org/fer/a"}
    )
    assert _find(errors_publish, "sections[0].questions[0]", "no_answer_path") is None


def test_inline_fer_pt_br_only_label_accepted(settings):
    """spec §1.2 rule 12 / §7 A7: an inlineFers label need not carry `en`."""
    doc = _base_doc()
    doc["inlineFers"] = [
        {
            "id": "https://fipm.example.org/fers/draft/55c036a2b284564b",
            "label": {"pt-BR": "Vocabulário do Ministério da Saúde"},
            "type": "structured-vocabulary",
            "homepage": None,
        }
    ]
    errors = validate_content(doc, publishing=True, settings=settings, known_fer_ids=set())
    assert errors == [], errors


def test_inline_fer_empty_label_rejected(settings):
    doc = _base_doc()
    doc["inlineFers"] = [
        {
            "id": "https://fipm.example.org/fers/draft/x",
            "label": {},
            "type": "structured-vocabulary",
        }
    ]
    errors = validate_content(doc, settings=settings, known_fer_ids=set())
    hit = _find(errors, "inlineFers[0].label", "missing_key")
    assert hit is not None, errors


def test_inline_fer_duplicates_catalogue_rejected(settings):
    known_id = "https://w3id.org/np/doi"
    doc = _base_doc()
    doc["inlineFers"] = [{"id": known_id, "label": {"en": "DOI"}, "type": "identifier-service"}]
    errors = validate_content(doc, settings=settings, known_fer_ids={known_id})
    hit = _find(errors, "inlineFers[0].id", "inline_fer_duplicates_catalogue")
    assert hit is not None, errors


def test_inline_fer_duplicates_catalogue_still_rejected_without_sources(settings):
    """No `known_fer_sources` supplied at all (the importer/TS-mirror shape)
    behaves exactly as before: still flagged."""
    known_id = "https://fipm.example.org/fers/draft/already-seed"
    doc = _base_doc()
    doc["inlineFers"] = [{"id": known_id, "label": {"en": "X"}, "type": "identifier-service"}]
    errors = validate_content(doc, settings=settings, known_fer_ids={known_id})
    assert _find(errors, "inlineFers[0].id", "inline_fer_duplicates_catalogue") is not None


def test_inline_fer_duplicates_catalogue_rejected_when_source_is_not_model(settings):
    """Review finding 1: the bypass is specific to source="model" -- a
    catalogue collision with a seed/user/user-promoted row is still a
    genuine duplicate."""
    known_id = "https://fipm.example.org/fers/draft/seed-clash"
    doc = _base_doc()
    doc["inlineFers"] = [{"id": known_id, "label": {"en": "X"}, "type": "identifier-service"}]
    errors = validate_content(
        doc,
        settings=settings,
        known_fer_ids={known_id},
        known_fer_sources={known_id: "seed"},
    )
    assert _find(errors, "inlineFers[0].id", "inline_fer_duplicates_catalogue") is not None


def test_inline_fer_duplicates_catalogue_bypassed_when_source_is_model(settings):
    """Review finding 1: re-validating a model whose own inlineFers entry
    was already promoted into the catalogue (source="model", same id) must
    not treat that as a fresh duplicate -- this is what makes a re-publish
    (or a PUT .../content resubmitting the same, already-promoted, entry)
    idempotent instead of permanently 400ing."""
    promoted_id = "https://fipm.example.org/fers/draft/already-promoted"
    doc = _base_doc()
    doc["inlineFers"] = [
        {"id": promoted_id, "label": {"en": "Already promoted"}, "type": "identifier-service"}
    ]
    errors = validate_content(
        doc,
        settings=settings,
        known_fer_ids={promoted_id},
        known_fer_sources={promoted_id: "model"},
    )
    assert _find(errors, "inlineFers[0].id", "inline_fer_duplicates_catalogue") is None
    assert errors == [], errors


def test_no_answer_path_skips_hidden_questions(settings):
    """Review finding 11: a hidden question is never shown to a respondent,
    so `allowFreeText: false` with no `suggestedFerIds` must not block
    publish for it."""
    doc = _base_doc()
    doc["sections"][0]["questions"][0]["allowFreeText"] = False
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = []
    doc["sections"][0]["questions"][0]["hidden"] = True

    errors_publish = validate_content(doc, publishing=True, settings=settings)
    assert _find(errors_publish, "sections[0].questions[0]", "no_answer_path") is None


def test_default_declaration_status_and_compact_declarations_validated(settings):
    doc = _base_doc()
    doc["defaultDeclarationStatus"] = "not-a-real-status"
    doc["compactDeclarations"] = "yes"
    errors = validate_content(doc, settings=settings)
    assert _find(errors, "defaultDeclarationStatus", "invalid_value") is not None
    assert _find(errors, "compactDeclarations", "invalid_value") is not None


def test_valid_picklist_document_has_no_errors(settings):
    doc = _base_doc()
    doc["defaultDeclarationStatus"] = "current"
    doc["compactDeclarations"] = True
    doc["inlineFers"] = [
        {
            "id": "https://fipm.example.org/fers/draft/55c036a2b284564b",
            "label": {"pt-BR": "Vocabulário do Ministério da Saúde"},
            "type": "structured-vocabulary",
        }
    ]
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = [
        "https://fipm.example.org/fers/draft/55c036a2b284564b",
        "https://w3id.org/np/doi",
    ]
    doc["sections"][0]["questions"][0]["allowFreeText"] = True
    errors = validate_content(
        doc, publishing=True, settings=settings, known_fer_ids={"https://w3id.org/np/doi"}
    )
    assert errors == [], errors
