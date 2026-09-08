"""AC14 (static shape check): the CI workflow declares the three required jobs
with the right commands. "CI is green" and the built-image checks (docker run
with only FIPM_DB_PATH set, `GET /` and `GET /api/health`) are verified by
actually running these commands / by CI itself, not by this unit test — this
suite does not invoke `docker build` per the task's instructions."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_declares_required_jobs_and_commands():
    workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow_path.is_file(), "expected .github/workflows/ci.yml"
    text = workflow_path.read_text(encoding="utf-8")

    for job in ("backend:", "frontend:", "docker:"):
        assert job in text, f"missing job {job!r}"

    assert "ruff check" in text
    assert "ruff format --check" in text
    assert "pytest" in text
    assert "npm ci" in text
    assert "npm run type-check" in text
    assert "npm run build" in text
    assert "docker build" in text
    assert "push" in text and "pull_request" in text
