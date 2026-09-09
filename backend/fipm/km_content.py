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
from urllib.parse import urlparse

from fipm.config import DECLARATION_STATUSES, Settings, get_settings
from fipm.fer_types import allowed_fer_type_keys

logger = logging.getLogger(__name__)

# Review finding 8: log the "taxonomy missing, skipping ferType validation"
# warning once per process, not once per validate_content() call.
_fer_type_warning_logged = False

# Question/section id pattern (spec 04 §2 "add question", §3.3 rule 2).
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Knowledge-model id pattern (spec 04 §1 "Model ids").
MODEL_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$")

LANGUAGES: frozenset[str] = frozenset({"en", "pt-PT", "pt-BR", "es"})

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

# spec 08-workshop-picklists.md §1.1/§1.2.
MAX_SUGGESTED_FER_IDS = 12
MAX_INLINE_FERS = 300

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


class ContentError(TypedDict):
    path: str
    code: str
    message: str


def _err(errors: list[ContentError], path: str, code: str, message: str) -> None:
    errors.append({"path": path, "code": code, "message": message})


def _is_absolute_http_iri(value: Any) -> bool:
    """spec 08 §1.2 rule 9/12: an absolute `http(s)` IRI, no whitespace or
    control characters."""
    if not isinstance(value, str) or not value or _CONTROL_CHAR_RE.search(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _check_langmap(
    value: Any,
    path: str,
    errors: list[ContentError],
    *,
    required: bool = True,
    require_en: bool = True,
    max_len: int | None = None,
) -> None:
    """Rule 3: a LangMap is an object of `str -> non-empty str` whose keys
    are within {en, pt-PT, pt-BR, es}. By default it must contain `en`
    (`require_en=True`); spec 08 §1.2 rule 12 / §3.1 relax that for an
    `inlineFers` label or a session area label (pt-BR-only sources), where
    the LangMap need only be non-empty. `max_len` overrides `MAX_TEXT_LEN`
    per-language (spec 08 §3.1: an area label is capped at 80 chars)."""
    limit = max_len if max_len is not None else MAX_TEXT_LEN
    if value is None:
        if required:
            _err(errors, path, "missing_key", f"{path} is required")
        return
    if not isinstance(value, dict):
        _err(errors, path, "missing_key", f"{path} must be an object")
        return
    if not require_en and not value:
        _err(errors, path, "missing_key", f"{path} must be non-empty")
        return
    for lang, text in value.items():
        if lang not in LANGUAGES:
            _err(errors, f"{path}.{lang}", "unknown_language", f"unknown language {lang!r}")
            continue
        if not isinstance(text, str) or text == "":
            _err(errors, f"{path}.{lang}", "empty_string", f"{path}.{lang} must be non-empty")
            continue
        if len(text) > limit:
            _err(errors, f"{path}.{lang}", "too_long", f"{path}.{lang} exceeds {limit} characters")
    if require_en and "en" not in value:
        _err(errors, path, "missing_en", f"{path} must include an 'en' entry")


def validate_langmap(
    value: Any,
    path: str,
    *,
    required: bool = True,
    require_en: bool = True,
    max_len: int | None = None,
) -> list[ContentError]:
    """Public single-field entry point (used by PATCH metadata updates that
    don't carry a full `content` document to run through `validate_content`,
    and by spec 08 §3.1 session `questionnaireRefs[].label` validation)."""
    errors: list[ContentError] = []
    _check_langmap(value, path, errors, required=required, require_en=require_en, max_len=max_len)
    return errors


def _validate_inline_fers(
    doc: dict[str, Any],
    errors: list[ContentError],
    *,
    fer_types: set[str],
    skip_fer_type_check: bool,
    known_fer_ids: set[str] | None,
) -> set[str]:
    """spec 08-workshop-picklists.md §1.2 rule 12: `model.inlineFers`.
    Returns the set of ids declared (valid or not -- used by rule 10 to
    resolve `suggestedFerIds` against, so a malformed entry's id, if it has
    one, still counts as "declared" for that purpose)."""
    inline_fers = doc.get("inlineFers")
    ids: set[str] = set()
    if inline_fers is None:
        return ids
    if not isinstance(inline_fers, list):
        _err(errors, "inlineFers", "invalid_value", "inlineFers must be a list")
        return ids
    if len(inline_fers) > MAX_INLINE_FERS:
        _err(errors, "inlineFers", "too_many", f"more than {MAX_INLINE_FERS} inlineFers entries")

    seen_ids: set[str] = set()
    for idx, entry in enumerate(inline_fers):
        path = f"inlineFers[{idx}]"
        if not isinstance(entry, dict):
            _err(errors, path, "missing_key", "inlineFers entry must be an object")
            continue

        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            _err(errors, f"{path}.id", "missing_key", "inlineFers entry id is required")
        elif not _is_absolute_http_iri(entry_id):
            _err(errors, f"{path}.id", "invalid_fer_iri", f"invalid inlineFers id {entry_id!r}")
        elif entry_id in seen_ids:
            _err(
                errors, f"{path}.id", "duplicate_inline_fer", f"duplicate inlineFers id {entry_id}"
            )
        else:
            seen_ids.add(entry_id)
            ids.add(entry_id)
            if known_fer_ids is not None and entry_id in known_fer_ids:
                _err(
                    errors,
                    f"{path}.id",
                    "inline_fer_duplicates_catalogue",
                    f"{entry_id} already exists in the catalogue; reference it via "
                    "suggestedFerIds instead",
                )

        # spec §1.2 rule 12: `label` is a LangMap, non-empty, `en` NOT
        # required (an area FER may be pt-BR only -- spec §7 A7).
        _check_langmap(entry.get("label"), f"{path}.label", errors, require_en=False)

        entry_type = entry.get("type")
        if not skip_fer_type_check and entry_type not in fer_types:
            _err(errors, f"{path}.type", "unknown_fer_type", f"unknown fer type {entry_type!r}")

        homepage = entry.get("homepage")
        if homepage is not None and not _is_absolute_http_iri(homepage):
            _err(errors, f"{path}.homepage", "invalid_value", "homepage must be an absolute IRI")

    return ids


def _validate_suggested_fer_ids(
    question: dict[str, Any],
    q_path: str,
    errors: list[ContentError],
    *,
    known_ids: set[str] | None,
) -> None:
    """spec 08-workshop-picklists.md §1.2 rule 9/10: `question.
    suggestedFerIds`."""
    suggested = question.get("suggestedFerIds")
    if suggested is None:
        return
    path = f"{q_path}.suggestedFerIds"
    if not isinstance(suggested, list):
        _err(errors, path, "invalid_value", "suggestedFerIds must be a list")
        return
    if len(suggested) > MAX_SUGGESTED_FER_IDS:
        _err(errors, path, "too_many", f"more than {MAX_SUGGESTED_FER_IDS} suggestedFerIds")

    seen: set[str] = set()
    for idx, fer_id in enumerate(suggested):
        item_path = f"{path}[{idx}]"
        if not isinstance(fer_id, str) or not _is_absolute_http_iri(fer_id):
            _err(errors, item_path, "invalid_fer_iri", f"invalid suggested FER id {fer_id!r}")
            continue
        if fer_id in seen:
            _err(errors, item_path, "duplicate_suggested_fer", f"duplicate suggested FER {fer_id}")
            continue
        seen.add(fer_id)
        # Rule 10: resolution is only checked when a catalogue snapshot was
        # supplied; `known_ids is None` means "skip resolution entirely"
        # (the importer/TS mirror/routers each supply their own known_ids).
        if known_ids is not None and fer_id not in known_ids:
            _err(errors, item_path, "unknown_suggested_fer", f"unresolved suggested FER {fer_id}")


def validate_content(
    doc: dict[str, Any],
    *,
    publishing: bool = False,
    settings: Settings | None = None,
    known_fer_ids: set[str] | None = None,
) -> list[ContentError]:
    """Validate a knowledge-model `content` document. Rules per spec 04
    §3.3 and spec 08-workshop-picklists.md §1.2 (rules 9-13). Returns at
    most `MAX_ERRORS` entries. `publishing=True` also enforces rule 8 (at
    least one non-hidden question) and rule 13 (every question must have an
    answer path). `known_fer_ids` is the caller's catalogue snapshot (a
    `SELECT id FROM fers` for the routers, `seed.json` for the importer,
    the picker's cached map for the TS mirror) used to resolve
    `suggestedFerIds`/`inlineFers` against; this function stays pure and
    does no I/O of its own -- `known_fer_ids=None` (the default) skips that
    resolution check entirely."""
    settings = settings or get_settings()
    errors: list[ContentError] = []

    _check_langmap(doc.get("title"), "title", errors)
    _check_langmap(doc.get("description"), "description", errors)

    fer_types_for_inline = allowed_fer_type_keys(settings)
    inline_fer_ids = _validate_inline_fers(
        doc,
        errors,
        fer_types=fer_types_for_inline,
        skip_fer_type_check=not fer_types_for_inline,
        known_fer_ids=known_fer_ids,
    )

    default_status = doc.get("defaultDeclarationStatus")
    if default_status is not None and default_status not in DECLARATION_STATUSES:
        _err(
            errors,
            "defaultDeclarationStatus",
            "invalid_value",
            f"defaultDeclarationStatus must be one of {DECLARATION_STATUSES}",
        )

    for bool_field in ("compactDeclarations",):
        v = doc.get(bool_field)
        if v is not None and not isinstance(v, bool):
            _err(errors, bool_field, "invalid_value", f"{bool_field} must be a boolean")

    known_suggested_ids = None if known_fer_ids is None else (inline_fer_ids | known_fer_ids)

    sections = doc.get("sections")
    if not isinstance(sections, list):
        _err(errors, "sections", "missing_key", "sections must be a list")
        sections = []

    if len(sections) > MAX_SECTIONS:
        _err(errors, "sections", "too_many", f"more than {MAX_SECTIONS} sections")

    fer_types = fer_types_for_inline
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

            for bool_field in ("required", "allowMultiple", "hidden", "allowFreeText"):
                v = question.get(bool_field)
                if v is not None and not isinstance(v, bool):
                    _err(
                        errors,
                        f"{q_path}.{bool_field}",
                        "invalid_value",
                        f"{bool_field} must be a boolean",
                    )

            _validate_suggested_fer_ids(question, q_path, errors, known_ids=known_suggested_ids)

            if publishing:
                allow_free_text = question.get("allowFreeText")
                suggested_ids = question.get("suggestedFerIds") or []
                if allow_free_text is False and not suggested_ids:
                    _err(
                        errors,
                        q_path,
                        "no_answer_path",
                        "a question with allowFreeText: false needs at least one "
                        "suggestedFerIds entry to be answerable",
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
