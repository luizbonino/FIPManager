"""Privacy-notice content: per-language markdown under data/i18n/privacy/
(spec 05-v1-completion.md §2), shared by `routers/privacy.py` (the full
notice) and `routers/auth.py` (the version registration must match).

The spec text describes one shared `data/i18n/privacy/version.json`
(`{"version": "1.0", "date": "2026-09-12"}`). The `data/i18n/privacy/*.md`
files actually shipped instead each start with an identical
`<!-- version: YYYY-MM-DD -->` HTML comment (no `version.json` on disk), and
this backend change may only *read* those files, not add to `data/` -- so
that comment is read as the notice's `version`. See the builder report for
this assumption.

Review finding 11: `PrivacyOut.date` used to just be a second copy of
`version`, unconditionally -- harmless for the real `*.md` files, whose
header comment already *is* a `YYYY-MM-DD` date, but wrong in spirit (`date`
duplicating a free-text `version` field rather than being validated as a
date) and actively wrong for a malformed file missing the header comment,
where `_load` falls back to the literal string `"unknown"` for `version` --
`date` would then read `"unknown"` too, which is not a date.
`privacy_notice_date` below only echoes the header value into `date` when it
actually parses as `YYYY-MM-DD`; otherwise `date` is `""`. If a `*.md`
body's own human-readable date ever disagrees with the header, that's left
alone -- `date` reflects the header only, `markdown` is never rewritten.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from fipm.config import Settings, get_settings

_VERSION_COMMENT_RE = re.compile(r"^<!--\s*version:\s*(?P<version>\S+?)\s*-->\s*\n?")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# pt-PT <-> pt-BR, es -> en, and anything else (including "en" itself and an
# unknown lang) -> en only. Mirrors exporters.resolve_lang's fallback chain.
_LANG_FALLBACK_CHAIN: dict[str, tuple[str, ...]] = {
    "pt-PT": ("pt-PT", "pt-BR", "en"),
    "pt-BR": ("pt-BR", "pt-PT", "en"),
    "es": ("es", "en"),
    "en": ("en",),
}


@lru_cache
def _load(data_dir: str, lang: str) -> tuple[str, str] | None:
    """(version, markdown-without-header-comment) for `<data_dir>/i18n/
    privacy/<lang>.md`, or None if the file is missing. Cached per
    (data_dir, lang): notice content is static between deploys, like
    fer_types.get_fer_types."""
    path = Path(data_dir) / "i18n" / "privacy" / f"{lang}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = _VERSION_COMMENT_RE.match(text)
    if match:
        return match.group("version"), text[match.end() :]
    return "unknown", text


def resolve_privacy(settings: Settings, lang: str | None) -> tuple[str, str, str]:
    """(resolved_lang, version, markdown) for the requested `lang`, following
    the pt-PT<->pt-BR / es->en / unknown->en chain (spec 05 §2: "`lang`
    resolves through the usual chain ... anything unknown falls back to
    en"). Raises 503 privacy_notice_missing if even `en` is absent (fails
    loudly in CI, not silently in the room)."""
    chain = _LANG_FALLBACK_CHAIN.get(lang or "en", _LANG_FALLBACK_CHAIN["en"])
    for candidate in chain:
        loaded = _load(settings.data_dir, candidate)
        if loaded is not None:
            version, markdown = loaded
            return candidate, version, markdown
    raise HTTPException(status_code=503, detail="privacy_notice_missing")


def privacy_notice_date(version: str) -> str:
    """`version` echoed into `PrivacyOut.date` only when it parses as an ISO
    `YYYY-MM-DD` date (true for every shipped `*.md` header today); `""`
    otherwise, e.g. for the `"unknown"` fallback of a malformed file
    (review finding 11)."""
    return version if _ISO_DATE_RE.match(version) else ""


def current_privacy_version(settings: Settings | None = None) -> str:
    """The version `RegisterRequest.privacy_accepted_version` must match --
    `en.md`'s header comment, since it is required in every language."""
    if settings is None:
        settings = get_settings()
    _, version, _ = resolve_privacy(settings, "en")
    return version
