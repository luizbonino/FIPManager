"""Offline user guides: `docs/{participant,administrator}-guide[.lang].md`
(+ images under `docs/images/`) served in-app so the workshop's
offline-hotspot contingency doesn't need internet access to `docs/` on
GitHub. `docs/` stays the single source of truth -- nothing here copies
guide content into `data/`; `backend/fipm/config.py`'s `guides_dir` setting
just points at it (repo-root `docs/` locally, `/app/docs/` in the Docker
image per the `COPY docs/ /app/docs/` Dockerfile step).

Mirrors `fipm/privacy.py`'s structure: a small `_load`/`resolve_*` pair, the
same pt-PT<->pt-BR / es->en / unknown->en fallback chain (duplicated here
rather than imported, matching how `fipm/mail.py` and `fipm/privacy.py` each
keep their own copy), and the same "raise loudly if even en is missing"
posture -- a missing guide is a packaging bug, not a normal 404 for a
present-but-untranslated one (that's a fallback, not a miss).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from fipm.config import Settings, get_settings

# Only these two ids exist; anything else is 404, not a fallback.
GUIDE_IDS: tuple[str, ...] = ("participant", "administrator")

# Every language a guide *might* have. "en" ships as the bare filename
# (`participant-guide.md`); the others as `participant-guide.pt-PT.md` etc.
_ALL_LANGS: tuple[str, ...] = ("en", "pt-PT", "pt-BR", "es")

# pt-PT <-> pt-BR, es -> en, and anything else (including "en" itself and an
# unknown lang) -> en only. Mirrors fipm.privacy._LANG_FALLBACK_CHAIN /
# exporters.resolve_lang's fallback chain.
_LANG_FALLBACK_CHAIN: dict[str, tuple[str, ...]] = {
    "pt-PT": ("pt-PT", "pt-BR", "en"),
    "pt-BR": ("pt-BR", "pt-PT", "en"),
    "es": ("es", "en"),
    "en": ("en",),
}

# The guides link images as `![alt](images/foo.png)`; rewritten to the
# in-app endpoint so the frontend needs no knowledge of the docs/ layout.
# Deliberately narrow: the `(!\[[^\]]*\])` prefix requires this to be an
# *image* reference (`![alt](images/...)`), not a plain link that merely
# points into images/ (`[readme](images/README.md)`) -- the endpoint this
# rewrites to only ever serves `.png` files (see _IMAGE_FILENAME_RE), so
# rewriting a non-image link into it would just produce a dead link.
# In-page anchors (`](#section)`) and other links (`](other-guide.md)`,
# `](https://...)`) are untouched by this regex regardless.
_IMAGE_LINK_RE = re.compile(r"(!\[[^\]]*\])\(images/")

# Cross-document links the guides carry between each other (the
# administrator guide links to the participant guide and vice versa) are
# rewritten onto the equivalent in-app route, so following one from inside
# the app navigates instead of hitting safeHref's allowlist and rendering
# a dead `href="#"`. Matches an optional `./` prefix and an optional
# `.<lang>` suffix (`participant-guide.pt-BR.md`, etc.) so every language
# variant of a filename maps to the same route regardless of which
# language guide is linking to it.
_PARTICIPANT_GUIDE_LINK_RE = re.compile(r"\]\((?:\./)?participant-guide(?:\.[A-Za-z-]+)?\.md\)")
_ADMINISTRATOR_GUIDE_LINK_RE = re.compile(r"\]\((?:\./)?administrator-guide(?:\.[A-Za-z-]+)?\.md\)")

# Links into workshop/ (the facilitator script, the participant handout)
# point at documents this app does not serve in-app at all -- no route,
# no endpoint. Rendered as a normal link they would still pass safeHref's
# allowlist (a same-origin-looking relative path) only to 404, or fail it
# and render as a dead `href="#"` in a new tab. Neither is useful, so the
# link markup is stripped entirely and the label rendered as plain text.
_WORKSHOP_LINK_RE = re.compile(r"\[([^\]]+)\]\(workshop/[^)]+\)")

# Fenced code blocks (``` ... ```) are illustrative examples -- e.g. a
# snippet of guide markdown source quoted for the reader -- and must be
# rendered verbatim, so none of the link rewrites above should reach
# inside one. `re.DOTALL` lets `.` cross the block's internal newlines.
_FENCE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)

# Whitelist for GET /api/guides/images/{filename}: lowercase letters,
# digits, hyphens, ".png" only -- no path separators, no "..", no null
# byte, no other extension. Matched against the raw path parameter before
# any filesystem access.
_IMAGE_FILENAME_RE = re.compile(r"^[a-z0-9-]+\.png$")


def _guide_path(guides_dir: str, guide_id: str, lang: str) -> Path:
    suffix = "" if lang == "en" else f".{lang}"
    return Path(guides_dir) / f"{guide_id}-guide{suffix}.md"


@lru_cache
def _load(guides_dir: str, guide_id: str, lang: str) -> str | None:
    """Raw markdown for `<guides_dir>/<guide_id>-guide[.lang].md`, or None
    if that file doesn't exist. Cached per (guides_dir, guide_id, lang):
    guide content is static between deploys, like fer_types.get_fer_types
    and privacy._load."""
    path = _guide_path(guides_dir, guide_id, lang)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _rewrite_image_links(markdown: str) -> str:
    return _IMAGE_LINK_RE.sub(r"\1(/api/guides/images/", markdown)


def _rewrite_guide_links(markdown: str) -> str:
    markdown = _PARTICIPANT_GUIDE_LINK_RE.sub("](/guide)", markdown)
    markdown = _ADMINISTRATOR_GUIDE_LINK_RE.sub("](/guide/admin)", markdown)
    return markdown


def _strip_undocumented_links(markdown: str) -> str:
    return _WORKSHOP_LINK_RE.sub(r"\1", markdown)


def _apply_outside_fences(markdown: str, transform: Callable[[str], str]) -> str:
    """Apply `transform` everywhere in `markdown` except inside a fenced
    ``` code block, leaving fenced regions byte-for-byte untouched. An
    unclosed trailing fence (an odd number of ``` markers) has no matching
    close for _FENCE_BLOCK_RE to find, so its content falls into the final
    unfenced segment and *is* transformed -- the same "runs to EOF" posture
    the renderer itself takes for an unclosed fence."""
    pieces: list[str] = []
    pos = 0
    for m in _FENCE_BLOCK_RE.finditer(markdown):
        pieces.append(transform(markdown[pos : m.start()]))
        pieces.append(m.group(0))
        pos = m.end()
    pieces.append(transform(markdown[pos:]))
    return "".join(pieces)


def list_guides(settings: Settings | None = None) -> list[dict[str, object]]:
    """[{"id": ..., "languages": [...]}] for every guide id that has at
    least an `en` file, listing every language actually present on disk
    (not the fallback chain -- the point is to tell the frontend what's
    really there)."""
    if settings is None:
        settings = get_settings()
    items: list[dict[str, object]] = []
    for guide_id in GUIDE_IDS:
        langs = [
            lang for lang in _ALL_LANGS if _load(settings.guides_dir, guide_id, lang) is not None
        ]
        if langs:
            items.append({"id": guide_id, "languages": langs})
    return items


def resolve_guide(settings: Settings, guide_id: str, lang: str | None) -> tuple[str, str]:
    """(resolved_lang, markdown) for `guide_id` in the requested `lang`,
    following the pt-PT<->pt-BR / es->en / unknown->en chain. 404
    guide_not_found for an unknown guide_id; 503 guide_missing if even `en`
    is absent for a known id (a packaging bug, not a normal miss)."""
    if guide_id not in GUIDE_IDS:
        raise HTTPException(status_code=404, detail="guide_not_found")
    chain = _LANG_FALLBACK_CHAIN.get(lang or "en", _LANG_FALLBACK_CHAIN["en"])
    for candidate in chain:
        markdown = _load(settings.guides_dir, guide_id, candidate)
        if markdown is not None:
            markdown = _apply_outside_fences(markdown, _rewrite_image_links)
            markdown = _apply_outside_fences(markdown, _rewrite_guide_links)
            markdown = _apply_outside_fences(markdown, _strip_undocumented_links)
            return candidate, markdown
    raise HTTPException(status_code=503, detail="guide_missing")


def resolve_guide_image(settings: Settings, filename: str) -> Path:
    """Absolute path to `<guides_dir>/images/<filename>`, after validating
    `filename` against the strict whitelist and confirming the resolved
    path is actually inside the images directory. Raises 404 image_not_found
    for anything that fails either check or doesn't exist -- deliberately
    the same status for "invalid name" and "not found" so a path-traversal
    probe learns nothing about the filesystem."""
    if not _IMAGE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="image_not_found")
    images_dir = (Path(settings.guides_dir) / "images").resolve()
    candidate = (images_dir / filename).resolve()
    if candidate.parent != images_dir or not candidate.is_file():
        raise HTTPException(status_code=404, detail="image_not_found")
    return candidate
