"""spec 13-fip-dashboard.md §8.2: the opt-in scale test. Excluded from the
default run (`addopts = "-m 'not scale'"` in pyproject.toml); `uv run pytest
-m scale` opts in. `FIPM_TEST_SCALE_FIPS` controls N (default 2000).

Brief A's four views (coverage, gaps, adoption, evolution) and brief B's
`neighbours`/`clusters`/`map` are all asserted here for the **hard**
N+1-detector properties: exact, constant statement counts across
population size, and no repeated statement text. `neighbours` additionally
asserts its posting-row scan is bounded independent of N (§4.3's central
claim). Timings are recorded as the spec's own "soft" deliverable --
ceilings are loose, the numbers are what matters, for §7.4's later tuning
pass.

`convergence` is not measured as its own row here: spec §3.3 folds it into
`map`'s single response (there is no standalone `/convergence` route, and
the four similarity endpoints this brief ships are exactly `pair`,
`neighbours`, `clusters`, `map`), so its cost is already inside `map`'s own
6-statement, reported total rather than double-counted as a ninth row.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

SCALE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCALE_DIR.parent.parent

pytestmark = pytest.mark.scale

DEFAULT_N = 2000
EXPECTED_STATEMENT_COUNTS = {
    "coverage": 2,
    "gaps": 2,
    "adoption": 4,
    "evolution": 3,
    "neighbours": 4,
    "map": 6,
}
# clusters has no single spec-mandated count (§8.2 names one only for the
# other seven); still asserted constant-across-N and repeat-free below.
SOFT_STATEMENT_COUNT_VIEWS = ("clusters",)
N_QUESTIONNAIRE_VERSIONS = 5  # must match generate_fips.py


class _AdminViewer:
    """Duck-typed viewer: `resolve_population`/`_readable_individually_expr`
    only read `.id`/`.role`, never `isinstance(..., User)` -- an admin
    viewer here means the population isn't itself restricted by visibility,
    so its size genuinely scales with N (a `public`-only population would
    scale too, just by a smaller, visibility-dependent factor)."""

    id = "scale-test-admin"
    role = "admin"


def _generate(tmp_path: Path, n: int, seed: int) -> Path:
    db_path = tmp_path / f"scale-{n}-{seed}.db"
    result = subprocess.run(
        [
            sys.executable,
            str(SCALE_DIR / "generate_fips.py"),
            "--n",
            str(n),
            "--seed",
            str(seed),
            "--out",
            str(db_path),
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def _full_population_spec() -> dict:
    return {
        "include": [
            {"kind": "questionnaire", "id": "gofair-fip-mini", "version": f"1.{v}.0"}
            for v in range(N_QUESTIONNAIRE_VERSIONS)
        ]
    }


def _run_views(
    db_path: Path,
) -> tuple[dict[str, int], dict[str, list[str]], dict[str, float], int, dict[str, object]]:
    from fipm.dashboard.populations import parse_population_spec
    from fipm.dashboard.similarity_views import clusters_view, map_view, neighbours_view
    from fipm.dashboard.views import adoption_view, coverage_view, evolution_view, gaps_view

    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    spec = parse_population_spec(_full_population_spec())

    counts: dict[str, int] = {}
    statements: dict[str, list[str]] = {}
    wall_ms: dict[str, float] = {}
    extra: dict[str, object] = {}

    neighbours_debug: dict[str, object] = {}

    with SessionLocal() as db:
        subject_fip_id = db.execute(text("SELECT id FROM fips ORDER BY id LIMIT 1")).scalar()

    fns = {
        "coverage": lambda db: coverage_view(db, spec, _AdminViewer()),
        "gaps": lambda db: gaps_view(db, spec, _AdminViewer()),
        "adoption": lambda db: adoption_view(db, spec, _AdminViewer(), status="any"),
        "evolution": lambda db: evolution_view(db, spec, _AdminViewer()),
        "neighbours": lambda db: neighbours_view(
            db, spec, _AdminViewer(), fip_id=subject_fip_id, limit=20, debug=neighbours_debug
        ),
        "clusters": lambda db: clusters_view(db, spec, _AdminViewer()),
        "map": lambda db: map_view(db, spec, _AdminViewer()),
    }

    with SessionLocal() as db:
        for name, fn in fns.items():
            seen: list[str] = []

            def _cb(conn, cursor, statement, parameters, context, executemany, _seen=seen):
                _seen.append(statement)

            event.listen(engine, "after_cursor_execute", _cb)
            start = time.perf_counter()
            envelope = fn(db)
            wall_ms[name] = (time.perf_counter() - start) * 1000
            event.remove(engine, "after_cursor_execute", _cb)

            counts[name] = len(seen)
            statements[name] = seen
            assert envelope["data"] is not None  # sanity: the view actually ran

        fip_count = int(db.execute(text("SELECT COUNT(*) FROM fips")).scalar())

    extra["posting_rows_scanned"] = neighbours_debug.get("posting_rows_scanned")
    extra["neighbours_keys_used"] = neighbours_debug.get("keys_used")
    extra["neighbours_candidates_scored"] = neighbours_debug.get("candidates_scored")

    engine.dispose()
    return counts, statements, wall_ms, fip_count, extra


def test_scale_statement_counts_and_timings(tmp_path):
    n = int(os.environ.get("FIPM_TEST_SCALE_FIPS", DEFAULT_N))
    n_quarter = max(n // 4, 10)

    db_full = _generate(tmp_path, n, seed=1)
    db_quarter = _generate(tmp_path, n_quarter, seed=2)

    counts_full, statements_full, wall_full, fips_full, extra_full = _run_views(db_full)
    counts_quarter, statements_quarter, wall_quarter, fips_quarter, extra_quarter = _run_views(
        db_quarter
    )

    report: dict[str, object] = {
        "n": n,
        "n_quarter": n_quarter,
        "fips_full": fips_full,
        "fips_quarter": fips_quarter,
        "neighbours_posting": {
            "rows_scanned_at_n": extra_full["posting_rows_scanned"],
            "rows_scanned_at_n_quarter": extra_quarter["posting_rows_scanned"],
            "keys_used_at_n": extra_full["neighbours_keys_used"],
            "candidates_scored_at_n": extra_full["neighbours_candidates_scored"],
        },
        "views": {},
    }

    for view in (*EXPECTED_STATEMENT_COUNTS, *SOFT_STATEMENT_COUNT_VIEWS):
        expected = EXPECTED_STATEMENT_COUNTS.get(view)
        if expected is not None:
            # hard: the exact expected count, from spec §8.2.
            assert counts_full[view] == expected, (view, "N", counts_full[view], expected)
            assert counts_quarter[view] == expected, (view, "N/4", counts_quarter[view], expected)
        # hard: constant across population size -- the N+1 detector.
        assert counts_full[view] == counts_quarter[view], (
            view,
            counts_full[view],
            counts_quarter[view],
        )
        # hard: no statement text repeats within one view call.
        assert len(statements_full[view]) == len(set(statements_full[view])), view
        assert len(statements_quarter[view]) == len(set(statements_quarter[view])), view

        report["views"][view] = {
            "statement_count": counts_full[view],
            "wall_ms_at_n": round(wall_full[view], 2),
            "wall_ms_at_n_quarter": round(wall_quarter[view], 2),
            # soft ceiling: loose on purpose (CI hardware varies) -- the
            # number is the deliverable, not a strict gate.
            "under_soft_ceiling_3s": wall_full[view] < 3000,
        }

    # hard (§4.3/AC-5): neighbours' posting-row scan is bounded independent
    # of population size -- the same ceiling at N and at N/4.
    from fipm.config import get_settings

    settings = get_settings()
    posting_ceiling = settings.dashboard_posting_budget + settings.dashboard_candidate_cap * 60
    for label, extra in (("N", extra_full), ("N/4", extra_quarter)):
        scanned = extra["posting_rows_scanned"]
        assert scanned is not None, label
        assert scanned <= posting_ceiling, (label, scanned, posting_ceiling)

    report["db_file_size_bytes_at_n"] = db_full.stat().st_size

    last_run_path = SCALE_DIR / "last-run.json"
    last_run_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    baseline_path = SCALE_DIR / "baseline.json"
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        for view in EXPECTED_STATEMENT_COUNTS:
            base_ms = baseline.get("views", {}).get(view, {}).get("wall_ms_at_n")
            if base_ms:
                # A regression gate: fail only on a > 3x regression.
                assert report["views"][view]["wall_ms_at_n"] < base_ms * 3, view
    else:
        baseline_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
