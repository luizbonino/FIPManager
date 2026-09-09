"""GET /api/privacy?lang=: privacy notice content by language (spec
05-v1-completion.md §2)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from fipm.config import get_settings
from fipm.privacy import privacy_notice_date, resolve_privacy
from fipm.schemas import PrivacyOut

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("", response_model=PrivacyOut)
def get_privacy(response: Response, lang: str | None = None) -> PrivacyOut:
    settings = get_settings()
    resolved_lang, version, markdown = resolve_privacy(settings, lang)
    rendered = markdown.replace("{{CONTACT_EMAIL}}", settings.contact_email).replace(
        "{{HOSTING_ORG}}", settings.hosting_org
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    # Review finding 11: `date` is only ever the header's ISO date, not a
    # duplicated free-text `version` -- see fipm.privacy.privacy_notice_date.
    return PrivacyOut(
        version=version,
        date=privacy_notice_date(version),
        lang=resolved_lang,
        markdown=rendered.strip(),
    )
