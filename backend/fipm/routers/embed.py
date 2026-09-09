"""GET /fips/{id}/embed -- outside /api (spec 06-dmp-linkage.md §3), so the
URL is quotable next to the FIP URL. Must be included in `main.py` with the
other routers, before the `@app.get("/{path:path}")` SPA catch-all is
defined, or the catch-all swallows it."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from fipm.authz import optional_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.embed import embed_headers, render_embed, render_not_found, resolve_embed_lang
from fipm.exporters import build_export_json
from fipm.models import KnowledgeModel, User
from fipm.routers.fips import _get_readable_fip

router = APIRouter(tags=["embed"])


@router.get("/fips/{fip_id}/embed", include_in_schema=False)
def embed_fip(
    fip_id: str,
    request: Request,
    lang: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> Response:
    settings = get_settings()
    try:
        # Auth = spec 01 §5's read rule, reused verbatim: owner, admin and
        # session owner by cookie, X-Edit-Token still honoured, and for an
        # anonymous caller only visibility link/public.
        fip = _get_readable_fip(fip_id, request, db, user)
    except HTTPException:
        html_body = render_not_found(settings, resolve_embed_lang(lang, "en"))
        headers = embed_headers(settings, visibility=None)
        headers.pop("Content-Type", None)
        return Response(
            content=html_body,
            media_type="text/html; charset=utf-8",
            status_code=404,
            headers=headers,
        )

    km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    doc = build_export_json(db, fip, settings)
    html_body = render_embed(doc, fip, settings, lang, km_license=km.license if km else None)
    headers = embed_headers(settings, visibility=fip.visibility)
    headers.pop("Content-Type", None)
    return Response(
        content=html_body,
        media_type="text/html; charset=utf-8",
        status_code=200,
        headers=headers,
    )
