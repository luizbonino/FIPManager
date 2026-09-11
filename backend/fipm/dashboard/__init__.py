"""spec 13-fip-dashboard.md: the dashboard backend. `populations.py` (§2)
resolves a population spec to an authorized set of FIP ids in one
statement; `views.py` (§3.1/§3.2/§3.4/§3.5) turns a resolved population into
the four brief-A views, each behind the §1.8 degrade ladder; `csvout.py`
(§3.6) streams the same aggregate as CSV. Similarity (§4), snapshots (§5)
and network ingestion land in brief B."""

from __future__ import annotations


class DashboardError(Exception):
    """Carries a full JSON error body (not just a single `detail` string) up
    to `routers/dashboard.py`, which turns it into a `JSONResponse` --
    spec §2.4/§1.8's error bodies (`population_too_small`, `projection_
    stale`, ...) are flat objects with extra fields alongside `detail`,
    which plain `HTTPException(detail=...)` cannot express (FastAPI nests a
    non-string `detail` one level deeper than the spec's examples show)."""

    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        super().__init__(body.get("detail"))
        self.status_code = status_code
        self.body = body
