from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

from fastapi import APIRouter, HTTPException

from fipm import __version__
from fipm.config import get_settings
from fipm.db import SCHEMA_VERSION
from fipm.privacy import resolve_privacy
from fipm.schemas import HealthOut, Language

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    settings = get_settings()
    # spec 05-v1-completion.md §2/§4: additive fields the frontend can read
    # from health instead of a dedicated /api/config. privacy_version is
    # None (not a 503) if the notice is missing -- health must stay up even
    # when data/i18n/privacy/en.md doesn't.
    try:
        _, privacy_version, _ = resolve_privacy(settings, "en")
    except HTTPException:
        privacy_version = None
    return HealthOut(
        status="ok",
        version=__version__,
        schema_version=SCHEMA_VERSION,
        time=datetime.now(UTC),
        contact_email=settings.contact_email,
        hosting_org=settings.hosting_org,
        feedback_enabled=settings.feedback_enabled,
        privacy_version=privacy_version,
        languages=list(get_args(Language)),
        network_enabled=settings.network_enabled,
    )
