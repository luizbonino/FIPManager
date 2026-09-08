"""Knowledge-model content validation and small shared helpers.

See docs/specs/04-knowledge-model-editor.md §3.3. `validate_content` is the
single source of truth for whether a knowledge-model `content` document (the
whole file shape of spec 01-foundations.md §3) is well-formed; it is used by
both the importer (`fipm.importer`) and the knowledge-models API
(`fipm.routers.knowledge_models`) so disk and API agree, and is mirrored in
`frontend/src/lib/kmContent.ts`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from typing import Any, TypedDict

from fipm.config import Settings, get_settings
from fipm.fer_types import allowed_fer_type_keys

logger = logging.getLogger(__name__)

# Review finding 8: log the "taxonomy missing, skipping ferType validation"
# warning once per process, not once per validate_content() call.
_fer_type_warning_logged = False

# Question/section id pattern (spec 04 §2 "add question", §3.3 rule 2).
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Knowledge-model id pattern (spec 04 §1 "Model ids").
MODEL_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$")

LANGUAGES: frozenset[str] = frozenset({"en", "pt-PT", "pt-BR"})

# spec 04 §3.3 rule 5: whitelist of FAIR principle ids a question may cite.
PRINCIPLES: frozenset[str] = frozenset(
    {
        "F1",
        "F2",
        "F3",
        "F4",
        "A1",
        "A1.1",
        "A1.2",
        "A2",
        "I1",
        "I2",
        "I3",
        "R1",
        "R1.1",
        "R1.2",
        "R1.3",
    }
)

SCOPES: frozenset[str] = frozenset({"metadata", "data"})

MAX_SECTIONS = 50
MAX_QUESTIONS = 300
MAX_TEXT_LEN = 4000
MAX_ERRORS = 50

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ContentError(TypedDict):
    path: str
    code: str
    message: str


def _err(errors: list[ContentError], path: str, code: str, message: str) -> None:
    errors.append({"path": path, "code": code, "message": message})


def _check_langmap(
    value: Any, path: str, errors: list[ContentError], *, required: bool = True
) -> None:
    """Rule 3: a LangMap is an object of `str -> non-empty str` whose keys
    are within {en, pt-PT, pt-BR} and contains `en`."""
    if value is None:
        if required:
            _err(errors, path, "missing_key", f"{path} is required")
        return
    if not isinstance(value, dict):
        _err(errors, path, "missing_key", f"{path} must be an object")
        return
    for lang, text in value.items():
        if lang not in LANGUAGES:
            _err(errors, f"{path}.{lang}", "unknown_language", f"unknown language {lang!r}")
            continue
        if not isinstance(text, str) or text == "":
            _err(errors, f"{path}.{lang}", "empty_string", f"{path}.{lang} must be non-empty")
            continue
        if len(text) > MAX_TEXT_LEN:
            _err(
                errors,
                f"{path}.{lang}",
                "too_long",
                f"{path}.{lang} exceeds {MAX_TEXT_LEN} characters",
            )
    if "en" not in value:
        _err(errors, path, "missing_en", f"{path} must include an 'en' entry")


def validate_langmap(value: Any, path: str, *, required: bool = True) -> list[ContentError]:
    """Public single-field entry point (used by PATCH metadata updates that
    don't carry a full `content` document to run through `validate_content`)."""
    errors: list[ContentError] = []
    _check_langmap(value, path, errors, required=required)
    return errors


def validate_content(
    doc: dict[str, Any], *, publishing: bool = False, settings: Settings | None = None
) -> list[ContentError]:
    """Validate a knowledge-model `content` document. Rules per spec 04
    §3.3. Returns at most `MAX_ERRORS` entries. `publishing=True` also
    enforces rule 8 (at least one non-hidden question)."""
    settings = settings or get_settings()
    errors: list[ContentError] = []

    _check_langmap(doc.get("title"), "title", errors)
    _check_langmap(doc.get("description"), "description", errors)

    sections = doc.get("sections")
    if not isinstance(sections, list):
        _err(errors, "sections", "missing_key", "sections must be a list")
        sections = []

    if len(sections) > MAX_SECTIONS:
        _err(errors, "sections", "too_many", f"more than {MAX_SECTIONS} sections")

    fer_types = allowed_fer_type_keys(settings)
    skip_fer_type_check = not fer_types
    if skip_fer_type_check:
        # Review finding 8: an empty taxonomy (data/fers/fer-types.json
        # missing, e.g. data/ not checked out yet) must not fail every
        # model that happens to set a ferType -- skip the rule instead,
        # once, with a warning.
        global _fer_type_warning_logged
        if not _fer_type_warning_logged:
            logger.warning(
                "FER type taxonomy is empty (data/fers/fer-types.json missing or "
                "unreadable); skipping ferType validation"
            )
            _fer_type_warning_logged = True

    section_ids: set[Any] = set()
    question_ids: set[Any] = set()
    total_questions = 0

    for s_idx, section in enumerate(sections):
        if len(errors) >= MAX_ERRORS:
            # Review finding 14: an oversized/adversarial document must not
            # make validate_content do unbounded work building an error list
            # that gets truncated anyway -- stop as soon as we've collected
            # enough to answer "invalid" (counts below, e.g. total_questions,
            # become approximate from this point on; that's fine, the
            # document is already conclusively invalid).
            break
        s_path = f"sections[{s_idx}]"
        if not isinstance(section, dict):
            _err(errors, s_path, "missing_key", "section must be an object")
            continue

        sec_id = section.get("id")
        if sec_id is None:
            _err(errors, f"{s_path}.id", "missing_key", "section id is required")
        elif not isinstance(sec_id, str) or not ID_PATTERN.match(sec_id):
            _err(errors, f"{s_path}.id", "invalid_id", f"invalid section id {sec_id!r}")
        elif sec_id in section_ids:
            _err(errors, f"{s_path}.id", "duplicate_section_id", f"duplicate section id {sec_id}")
        else:
            section_ids.add(sec_id)

        _check_langmap(section.get("title"), f"{s_path}.title", errors)

        questions = section.get("questions")
        if not isinstance(questions, list):
            _err(errors, f"{s_path}.questions", "missing_key", "questions must be a list")
            questions = []

        for q_idx, question in enumerate(questions):
            if len(errors) >= MAX_ERRORS:
                break
            q_path = f"{s_path}.questions[{q_idx}]"
            total_questions += 1
            if not isinstance(question, dict):
                _err(errors, q_path, "missing_key", "question must be an object")
                continue

            q_id = question.get("id")
            if q_id is None:
                _err(errors, f"{q_path}.id", "missing_key", "question id is required")
            elif not isinstance(q_id, str) or not ID_PATTERN.match(q_id):
                _err(errors, f"{q_path}.id", "invalid_id", f"invalid question id {q_id!r}")
            elif q_id in question_ids:
                _err(
                    errors, f"{q_path}.id", "duplicate_question_id", f"duplicate question id {q_id}"
                )
            else:
                question_ids.add(q_id)

            _check_langmap(question.get("text"), f"{q_path}.text", errors)
            if question.get("help") is not None:
                _check_langmap(question.get("help"), f"{q_path}.help", errors)

            fer_type = question.get("ferType")
            if not skip_fer_type_check and fer_type is not None and fer_type not in fer_types:
                _err(
                    errors,
                    f"{q_path}.ferType",
                    "unknown_fer_type",
                    f"unknown ferType {fer_type!r}",
                )

            principle = question.get("principle")
            if principle is not None and principle not in PRINCIPLES:
                _err(
                    errors,
                    f"{q_path}.principle",
                    "unknown_principle",
                    f"unknown principle {principle!r}",
                )

            scope = question.get("scope")
            if scope is not None and scope not in SCOPES:
                _err(errors, f"{q_path}.scope", "invalid_value", f"invalid scope {scope!r}")

            for bool_field in ("required", "allowMultiple", "hidden"):
                v = question.get(bool_field)
                if v is not None and not isinstance(v, bool):
                    _err(
                        errors,
                        f"{q_path}.{bool_field}",
                        "invalid_value",
                        f"{bool_field} must be a boolean",
                    )

    if total_questions > MAX_QUESTIONS:
        _err(errors, "sections", "too_many", f"more than {MAX_QUESTIONS} questions")

    if publishing:
        has_visible = any(
            isinstance(section, dict)
            and any(
                isinstance(q, dict) and q.get("hidden") is not True
                for q in (section.get("questions") or [])
            )
            for section in sections
        )
        if not has_visible:
            _err(
                errors,
                "sections",
                "no_visible_questions",
                "at least one non-hidden question is required to publish",
            )

    return errors[:MAX_ERRORS]


def content_sha256(doc: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()


def normalize_source(source: object) -> str:
    """The knowledge-model `source` field may be a plain string or a
    {"name", "url"} object (the real GO FAIR file uses the latter)."""
    if isinstance(source, dict):
        name = source.get("name")
        return str(name) if name else json.dumps(source, sort_keys=True)
    return str(source)


def slugify(text: str, max_len: int = 48) -> str:
    slug = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return slug[:max_len].strip("-")


def random_id_base(length: int = 6) -> str:
    """`length` lowercase Crockford base32 characters, for the `model-<...>`
    fallback id (spec 04 §1) when a title slugifies to nothing."""
    value = secrets.randbits(length * 5)
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_CROCKFORD_ALPHABET[rem])
    return "".join(reversed(chars)).lower()
