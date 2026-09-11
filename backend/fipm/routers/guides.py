"""GET /api/guides, /api/guides/{guide_id}, /api/guides/images/{filename}:
offline user guides (participant/administrator), served from docs/ so the
workshop's offline-hotspot contingency needs no internet access. Mirrors
routers/privacy.py's structure and error handling."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from fipm.config import get_settings
from fipm.guides import list_guides, resolve_guide, resolve_guide_image
from fipm.schemas import GuideListOut, GuideOut

router = APIRouter(prefix="/guides", tags=["guides"])


@router.get("", response_model=GuideListOut)
def get_guides() -> GuideListOut:
    settings = get_settings()
    return GuideListOut(items=list_guides(settings))


@router.get("/images/{filename}")
def get_guide_image(filename: str) -> FileResponse:
    settings = get_settings()
    path = resolve_guide_image(settings, filename)
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{guide_id}", response_model=GuideOut)
def get_guide(guide_id: str, lang: str | None = None) -> GuideOut:
    settings = get_settings()
    resolved_lang, markdown = resolve_guide(settings, guide_id, lang)
    return GuideOut(id=guide_id, language=resolved_lang, markdown=markdown)
