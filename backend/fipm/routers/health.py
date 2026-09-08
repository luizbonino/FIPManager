from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from fipm import __version__
from fipm.db import SCHEMA_VERSION
from fipm.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="ok", version=__version__, schema_version=SCHEMA_VERSION, time=datetime.now(UTC)
    )
