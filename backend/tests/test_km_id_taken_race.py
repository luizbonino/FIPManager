"""Review finding 13 (routers/knowledge_models._commit_or_id_taken): the
pre-insert `_id_in_use` check in `_validate_caller_id` is TOCTOU-racy -- two
concurrent requests can both pass it for the same id before either commits.
`_commit_or_id_taken` (used by create/fork/import's final `db.add(row);
db.commit()`) catches the resulting IntegrityError and turns it into 409
`model_id_taken` instead of an unhandled 500, and leaves the session usable
afterwards."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fipm.db import SessionLocal
from fipm.models import KnowledgeModel
from fipm.routers.knowledge_models import _commit_or_id_taken


def _km(id_: str, version: str = "1.0.0", *, sha: str) -> KnowledgeModel:
    return KnowledgeModel(
        id=id_,
        version=version,
        owner_id=None,
        visibility="public",
        status="draft",
        license="CC0-1.0",
        source="test",
        title={"en": id_},
        description={"en": id_},
        changelog=[],
        content={"id": id_, "version": version, "sections": []},
        content_sha256=sha,
    )


def test_integrity_error_on_commit_becomes_409_model_id_taken(db_session):
    first = _km("race-km", sha="first")
    db_session.add(first)
    db_session.commit()

    # A second, independent session -- like a concurrent request that read
    # "id not in use" before the first request's commit landed.
    with SessionLocal() as other_db:
        second = _km("race-km", sha="second")
        other_db.add(second)
        with pytest.raises(HTTPException) as exc_info:
            _commit_or_id_taken(other_db, second)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "model_id_taken"


def test_session_is_still_usable_after_the_rollback(db_session):
    first = _km("race-km-2", sha="first")
    db_session.add(first)
    db_session.commit()

    with SessionLocal() as other_db:
        second = _km("race-km-2", sha="second")
        other_db.add(second)
        with pytest.raises(HTTPException):
            _commit_or_id_taken(other_db, second)

        third = _km("race-km-3", sha="third")
        other_db.add(third)
        _commit_or_id_taken(other_db, third)  # must not raise

        assert other_db.get(KnowledgeModel, ("race-km-3", "1.0.0")) is not None
