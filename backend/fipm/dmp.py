"""FioDMP linkage: `relatedDMPs` normalisation/validation and `dmpEvidence`
validation (spec 06-dmp-linkage.md §1, §2).

One helper per concern, used by every write path (`POST /api/fips`,
`PATCH /api/fips/{id}`, `POST /api/fips/import`, and the prefill stub).
Validation deliberately lives here rather than in Pydantic field
validators, so failures keep the API-wide `{"detail": "<snake_case_code>"}`
shape (spec 01 §6) instead of Pydantic's error array.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from fipm.config import Settings, get_settings

MAX_RELATED_DMPS = 10
MAX_URL_LEN = 2048
MAX_VERSION_LEN = 20
MAX_SECTION_LEN = 40
MAX_QUESTION_REF_LEN = 120

# Any ASCII whitespace or control character (including the ones str.strip()
# would remove from the ends, but this also catches them mid-string).
_WHITESPACE_OR_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]")


def _fiodmp_host(settings: Settings) -> str:
    return (urlsplit(settings.fiodmp_base_url).hostname or "").lower()


def _fiodmp_pattern(settings: Settings) -> re.Pattern[str]:
    host = re.escape(_fiodmp_host(settings))
    return re.compile(rf"^https://(www\.)?{host}/(publico/)?(?P<id>[A-Za-z0-9]{{4,16}})$")


def _normalise_url(raw: Any, settings: Settings) -> str:
    """Trim; validate absolute https, non-empty host, no userinfo, no
    whitespace/control chars, <= 2048 chars; then lowercase scheme/host,
    drop a default port, an empty query and a fragment, and strip a
    trailing `/`. Raises HTTPException(422, "dmp_url_invalid") otherwise."""
    if not isinstance(raw, str) or not raw:
        raise HTTPException(status_code=422, detail="dmp_url_invalid")
    # Review finding 6: strip surrounding whitespace *before* scanning for
    # control characters, so a pasted URL with leading/trailing spaces (a
    # space is itself in the \x00-\x20 scan range) is accepted; an embedded
    # control/whitespace character still rejects.
    trimmed = raw.strip()
    if not trimmed or len(trimmed) > MAX_URL_LEN:
        raise HTTPException(status_code=422, detail="dmp_url_invalid")
    if _WHITESPACE_OR_CONTROL_RE.search(trimmed):
        raise HTTPException(status_code=422, detail="dmp_url_invalid")

    try:
        parsed = urlsplit(trimmed)
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="dmp_url_invalid") from exc

    if parsed.scheme.lower() != "https":
        raise HTTPException(status_code=422, detail="dmp_url_invalid")
    if "@" in (parsed.netloc or ""):
        raise HTTPException(status_code=422, detail="dmp_url_invalid")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=422, detail="dmp_url_invalid")

    if not host.isascii():
        # Review finding 7: `str.encode("idna")` silently *folds away*
        # format characters (zero-width space/joiners, category "Cf") and
        # collapses fullwidth/halfwidth compatibility variants onto plain
        # ASCII look-alikes instead of erroring on them -- left unchecked,
        # two visually distinct hosts (or a host smuggling an invisible
        # character) would normalise to the identical stored URL. Reject
        # those instead of letting idna quietly rewrite them; a genuine
        # non-ASCII hostname (e.g. "münchen.de") is unaffected by either
        # check and still round-trips through idna to its punycode form.
        if (
            any(unicodedata.category(ch) == "Cf" for ch in host)
            or unicodedata.normalize("NFKC", host) != host
        ):
            raise HTTPException(status_code=422, detail="dmp_url_invalid")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise HTTPException(status_code=422, detail="dmp_url_invalid") from exc
        if not host.isascii():
            raise HTTPException(status_code=422, detail="dmp_url_invalid")

    netloc = host.lower()
    if port is not None and port != 443:
        netloc = f"{netloc}:{port}"
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    elif path == "/":
        path = ""

    normalised = urlunsplit(("https", netloc, path, parsed.query, ""))
    if len(normalised) > MAX_URL_LEN:
        raise HTTPException(status_code=422, detail="dmp_url_invalid")
    return normalised


def _detect_system(url: str, settings: Settings) -> tuple[str, str | None]:
    match = _fiodmp_pattern(settings).match(url)
    if match:
        return "FioDMP", match.group("id").upper()
    return "other", None


def normalise_related_dmps(
    entries: list[dict[str, Any]], settings: Settings | None = None
) -> list[dict[str, Any]]:
    """Validate and normalise a FIP's `relatedDMPs` (spec 06 §1.1). `system`
    and `dmpId` are always derived server-side from the normalised URL --
    any client-sent `system`/`dmpId` on an entry is ignored/overwritten."""
    if settings is None:
        settings = get_settings()
    if len(entries) > MAX_RELATED_DMPS:
        raise HTTPException(status_code=422, detail="dmp_too_many")

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        url = _normalise_url(entry.get("url") if isinstance(entry, dict) else None, settings)
        system, dmp_id = _detect_system(url, settings)
        if system == "FioDMP":
            # The stored URL for a FioDMP plan is always the canonical
            # `https://<host>/<ID>` form, regardless of `www.`/`publico/`
            # or casing in what the client sent -- duplicate detection below
            # must use this canonical form too, not the pre-canonicalisation
            # one, so two casings of the same plan id collide.
            url = f"https://{_fiodmp_host(settings)}/{dmp_id}"

        if url in seen:
            raise HTTPException(status_code=422, detail="dmp_url_duplicate")
        seen.add(url)

        version = entry.get("version") if isinstance(entry, dict) else None
        if version is not None and (not isinstance(version, str) or len(version) > MAX_VERSION_LEN):
            raise HTTPException(status_code=422, detail="dmp_version_invalid")

        record: dict[str, Any] = {"url": url, "version": version, "system": system}
        if dmp_id is not None:
            record["dmpId"] = dmp_id
        out.append(record)
    return out


def _is_int_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def apply_dmp_evidence(
    answers: list[dict[str, Any]], related_dmps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate every declaration's `dmpEvidence` against `related_dmps`
    (spec 06 §2.2), collapsing an all-empty evidence object to `null`.
    Mutates and returns `answers`. Must run after `related_dmps` has
    already been normalised for this same request/transaction."""
    for answer in answers:
        for decl in answer.get("declarations") or []:
            raw = decl.get("dmpEvidence")
            if not raw:
                decl["dmpEvidence"] = None
                continue

            dmp_index = raw.get("dmpIndex")
            section = raw.get("section")
            question_ref = raw.get("questionRef")

            if dmp_index is None and section is None and question_ref is None:
                decl["dmpEvidence"] = None
                continue

            if not related_dmps:
                raise HTTPException(status_code=422, detail="dmp_evidence_without_dmp")
            if not _is_int_not_bool(dmp_index) or dmp_index < 0 or dmp_index >= len(related_dmps):
                raise HTTPException(status_code=422, detail="dmp_evidence_index_invalid")
            if section is not None and (
                not isinstance(section, str) or len(section) > MAX_SECTION_LEN
            ):
                raise HTTPException(status_code=422, detail="dmp_evidence_invalid")
            if question_ref is not None and (
                not isinstance(question_ref, str) or len(question_ref) > MAX_QUESTION_REF_LEN
            ):
                raise HTTPException(status_code=422, detail="dmp_evidence_invalid")

            decl["dmpEvidence"] = {
                "dmpIndex": dmp_index,
                "section": section,
                "questionRef": question_ref,
            }
    return answers


def normalise_legacy_dmp_evidence(
    answers: list[dict[str, Any]], related_dmps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Review finding 1: opportunistically migrate a legacy `{url,
    questionRef}` `dmpEvidence` object (spec 06 §2.4) to the current
    `{dmpIndex, section, questionRef}` shape whenever a PATCH gives us the
    chance to look at it -- match the stored `url` against `related_dmps`
    by exact (already-normalised) string equality and rewrite it as a
    `dmpIndex`; when it matches nothing currently related, drop the stale
    `url` rather than leave a shape around that `apply_dmp_evidence` can
    never validate (it has no `dmpIndex` to check). Never raises -- this is
    a best-effort repair, not validation. A dict already in the current
    shape (has no `url` key) is left untouched. Mutates and returns
    `answers`."""
    url_to_index = {d["url"]: i for i, d in enumerate(related_dmps)}
    for answer in answers:
        for decl in answer.get("declarations") or []:
            raw = decl.get("dmpEvidence")
            if not isinstance(raw, dict) or "url" not in raw:
                continue
            index = url_to_index.get(raw.get("url"))
            new_evidence = {k: v for k, v in raw.items() if k != "url"}
            if index is not None:
                new_evidence["dmpIndex"] = index
            decl["dmpEvidence"] = new_evidence
    return answers


def is_safe_https_url(raw: Any, settings: Settings | None = None) -> bool:
    """Review findings 2/7: defensive re-check for a value already sitting
    in storage (pre-validation data, or a legacy `dmpEvidence.url`) that is
    about to be rendered as a link or handed to a consumer as `dmpUrl`:
    true iff `raw` is still a valid, absolute https URL per
    `_normalise_url`'s rules. Never raises -- callers must degrade
    gracefully (plain text / null) rather than 500 on bad stored data."""
    if not isinstance(raw, str) or not raw:
        return False
    if settings is None:
        settings = get_settings()
    try:
        _normalise_url(raw, settings)
    except HTTPException:
        return False
    return True


def resolve_dmp_evidence_for_export(
    dmp_evidence: dict[str, Any] | None,
    related_dmps: list[dict[str, Any]],
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """spec 06 §2.4: resolve a stored `dmpEvidence` (new shape, index-based,
    or the legacy `{url, questionRef}` shape) into the export shape
    `{dmpIndex, dmpUrl, dmpSystem, dmpVersion, section, questionRef}`, so a
    consumer never needs the index. A legacy object (no resolvable
    `dmpIndex`) exports its `url` as `dmpUrl` only when that url is still a
    valid https URL (review finding 2); otherwise `dmpUrl` is null and the
    raw value is kept under `rawUrl` so a consumer can still see it without
    ever receiving a scheme (e.g. `javascript:`) that could render as a
    clickable link. An unresolvable index likewise collapses to a null
    `dmpUrl` while `section`/`questionRef` are always kept."""
    if not dmp_evidence:
        return None

    dmp_index = dmp_evidence.get("dmpIndex")
    dmp: dict[str, Any] | None = None
    if _is_int_not_bool(dmp_index) and related_dmps and 0 <= dmp_index < len(related_dmps):
        dmp = related_dmps[dmp_index]
    else:
        dmp_index = None

    result: dict[str, Any] = {
        "dmpIndex": dmp_index,
        "dmpUrl": dmp["url"] if dmp else None,
        "dmpSystem": dmp.get("system") if dmp else None,
        "dmpVersion": dmp.get("version") if dmp else None,
        "section": dmp_evidence.get("section"),
        "questionRef": dmp_evidence.get("questionRef"),
    }
    if dmp is None:
        raw_url = dmp_evidence.get("url")
        if raw_url:
            if is_safe_https_url(raw_url, settings):
                result["dmpUrl"] = raw_url
            else:
                result["rawUrl"] = raw_url
    return result
