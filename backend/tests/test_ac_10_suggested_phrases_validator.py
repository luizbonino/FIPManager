"""spec 10-suggested-phrases-and-other.md: `validate_content` rules for
`question.suggestedPhrases` -- the free-text options the co-facilitator
asked to keep visible per question instead of the importer silently
dropping generic/placeholder options ("skip" in data/workshop/option-
map.json). Pure unit tests against `km_content.validate_content`, mirroring
`test_ac_08_01_02_suggested_fer_validator.py`'s style."""

from __future__ import annotations

import copy

from fipm.km_content import MAX_SUGGESTED_PHRASES, validate_content


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


def _with_phrases(phrases) -> dict:
    doc = copy.deepcopy(_base_doc())
    doc["sections"][0]["questions"][0]["suggestedPhrases"] = phrases
    return doc


def _find(errors, path, code):
    return next((e for e in errors if e["path"] == path and e["code"] == code), None)


def _q_path() -> str:
    return "sections[0].questions[0].suggestedPhrases"


# ---------------------------------------------------------------------------
# Valid
# ---------------------------------------------------------------------------


def test_valid_phrases_accepted():
    doc = _with_phrases(
        [
            {"text": {"pt-BR": "Apenas texto não estruturado"}},
            {"text": {"pt-BR": "Conta do repositório", "en": "Repository account"}},
        ]
    )
    assert validate_content(doc) == []


def test_phrases_absent_is_fine():
    doc = _base_doc()
    assert validate_content(doc) == []


def test_phrases_coexist_with_suggested_fer_ids():
    doc = _with_phrases([{"text": {"pt-BR": "Frase livre"}}])
    doc["sections"][0]["questions"][0]["suggestedFerIds"] = ["https://www.doi.org/"]
    errors = validate_content(doc, known_fer_ids={"https://www.doi.org/"})
    assert errors == []


def test_up_to_max_phrases_accepted():
    phrases = [{"text": {"pt-BR": f"Frase {i}"}} for i in range(MAX_SUGGESTED_PHRASES)]
    doc = _with_phrases(phrases)
    assert validate_content(doc) == []


# ---------------------------------------------------------------------------
# Invalid
# ---------------------------------------------------------------------------


def test_too_many_phrases_rejected():
    phrases = [{"text": {"pt-BR": f"Frase {i}"}} for i in range(MAX_SUGGESTED_PHRASES + 1)]
    doc = _with_phrases(phrases)
    errors = validate_content(doc)
    hit = _find(errors, _q_path(), "too_many")
    assert hit is not None, errors


def test_empty_text_rejected():
    doc = _with_phrases([{"text": {"pt-BR": ""}}])
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[0].text.pt-BR", "empty_string")
    assert hit is not None, errors


def test_missing_text_rejected():
    doc = _with_phrases([{"text": None}])
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[0].text", "missing_key")
    assert hit is not None, errors


def test_duplicate_phrase_text_rejected():
    doc = _with_phrases(
        [
            {"text": {"pt-BR": "Mesma frase"}},
            {"text": {"en": "mesma   FRASE"}},
        ]
    )
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[1]", "duplicate_phrase")
    assert hit is not None, errors


def test_duplicate_phrase_across_languages_within_different_entries():
    doc = _with_phrases(
        [
            {"text": {"pt-BR": "Texto A", "en": "Text A"}},
            {"text": {"pt-PT": "texto a"}},
        ]
    )
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[1]", "duplicate_phrase")
    assert hit is not None, errors


def test_wrong_shape_not_a_list_rejected():
    doc = _with_phrases("not a list")
    errors = validate_content(doc)
    hit = _find(errors, _q_path(), "invalid_value")
    assert hit is not None, errors


def test_entry_not_an_object_rejected():
    doc = _with_phrases(["just a string"])
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[0]", "missing_key")
    assert hit is not None, errors


def test_untrimmed_text_rejected():
    doc = _with_phrases([{"text": {"pt-BR": "  Frase com espaços  "}}])
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[0].text.pt-BR", "not_trimmed")
    assert hit is not None, errors


def test_text_over_200_chars_rejected():
    doc = _with_phrases([{"text": {"pt-BR": "x" * 201}}])
    errors = validate_content(doc)
    hit = _find(errors, f"{_q_path()}[0].text.pt-BR", "too_long")
    assert hit is not None, errors


def test_text_does_not_require_en():
    """spec 08 §7 A7's pt-BR-only relaxation applies to phrase text too --
    the source document is pt-BR only."""
    doc = _with_phrases([{"text": {"pt-BR": "Só em português"}}])
    errors = validate_content(doc)
    assert not any(e["path"].startswith(f"{_q_path()}[0].text") for e in errors), errors
