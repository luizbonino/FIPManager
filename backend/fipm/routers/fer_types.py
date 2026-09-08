"""GET /api/fer-types: the FER-type taxonomy (spec 02-core-flows.md §5.2).

Public, no auth. Backed by fipm.fer_types.get_fer_types(), which loads
data/fers/fer-types.json (cached). The file is not bundled into the SPA
(frontend/tsconfig.json includes src/** only), so the FER-type chip needs
this endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from fipm.config import get_settings
from fipm.fer_types import get_fer_types

router = APIRouter(prefix="/fer-types", tags=["fer-types"])


@router.get("")
def list_fer_types(response: Response) -> dict[str, Any]:
    settings = get_settings()
    types = get_fer_types(settings)
    items = [
        {
            "key": t["key"],
            "iri": t.get("iri"),
            "principle": t.get("principle"),
            "label": t.get("label") or {},
            "description": t.get("description") or {},
        }
        for t in types.values()
    ]
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {"items": items, "total": len(items)}
