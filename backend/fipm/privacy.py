"""Privacy-notice content: per-language markdown under data/i18n/privacy/
(spec 05-v1-completion.md §2), shared by `routers/privacy.py` (the full
notice) and `routers/auth.py` (the version registration must match).

The spec text describes one shared `data/i18n/privacy/version.json`
(`{"version": "1.0", "date": "2026-09-12"}`). The `data/i18n/privacy/*.md`
files actually shipped instead each start with an identical
`<!-- version: YYYY-MM-DD -->` HTML comment (no `version.json` on disk), and
this backend change may only *read* those files, not add to `data/` -- so
that comment is read as both the notice's `version` and its `date`. See the
builder report for this assumption.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from fipm.config import Settings, get_settings

_VERSION_COMMENT_RE = re.compile(r"^<!--\s*version:\s*(?P<version>\S+?)\s*-->\s*\n?")

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


def current_privacy_version(settings: Settings | None = None) -> str:
    """The version `RegisterRequest.privacy_accepted_version` must match --
    `en.md`'s header comment, since it is required in every language."""
    if settings is None:
        settings = get_settings()
    _, version, _ = resolve_privacy(settings, "en")
    return version
