"""FER type taxonomy: loaded from data/fers/fer-types.json as a cached config list.

Not a DB table (no migration needed); used to validate the `type` field of
POST /api/fers against the FIP-ontology FER types when the taxonomy file is
present. Missing file => empty taxonomy => validation is skipped (data/ may
be empty or in flux).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fipm.config import Settings


@lru_cache
def _load(data_dir: str) -> dict[str, dict[str, Any]]:
    path = Path(data_dir) / "fers" / "fer-types.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {t["key"]: t for t in doc.get("types", []) if "key" in t}


def get_fer_types(settings: Settings) -> dict[str, dict[str, Any]]:
    return _load(settings.data_dir)


def allowed_fer_type_keys(settings: Settings) -> set[str]:
    return set(get_fer_types(settings).keys())
