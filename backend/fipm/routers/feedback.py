"""POST /api/feedback and the feedback GET routes (spec 05-v1-completion.md
§4). Anonymous by construction: no user_id, no IP, no edit token stored --
the client IP is used only by the rate limiter and discarded. CSRF applies
to the POST like every other write (spec 01 §4, via
`fipm.auth.csrf_middleware`, already mounted for all non-GET /api/*)."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from fipm.auth import check_feedback_rate_limit, client_ip, record_feedback_attempt
from fipm.authz import can_read, can_write_owned, optional_user, require_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.exporters import _iso_utc, _write_csv_row
from fipm.ids import new_feedback_id
from fipm.models import Feedback, Fip, User, WorkshopSession
from fipm.routers.sessions import _get_owned_session
from fipm.schemas import (
    FeedbackCommentOut,
    FeedbackCreateRequest,
    FeedbackQuestionStat,
    FeedbackSummaryOut,
)

router = APIRouter(tags=["feedback"])

FEEDBACK_CSV_HEADER = ["session_id", "created_at", "q1", "q2", "q3", "comment"]


@router.post("/feedback", status_code=201)
def post_feedback(
    body: FeedbackCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, str]:
    settings = get_settings()
    if not settings.feedback_enabled:
        raise HTTPException(status_code=403, detail="feedback_disabled")
    check_feedback_rate_limit(request)

    # Review finding 7: an unknown or unreadable sessionId/fipId used to
    # raise 404, which makes this public, unauthenticated endpoint an
    # existence oracle for guessing valid session/FIP ids (repeatedly POST
    # and watch 404 vs 201). Instead, silently store NULL for that field and
    # still record the feedback -- a readable id (owned by `user`, or
    # public/link visibility) is kept as given.
    session_id = body.session_id
    if session_id is not None and db.get(WorkshopSession, session_id) is None:
        session_id = None

    fip_id = body.fip_id
    if fip_id is not None:
        fip = db.get(Fip, fip_id)
        if fip is None or not can_read(fip.owner_id, fip.visibility, user):
            fip_id = None

    row = Feedback(
        id=new_feedback_id(),
        session_id=session_id,
        fip_id=fip_id,
        q1=body.q1,
        q2=body.q2,
        q3=body.q3,
        comment=body.comment,
        language=body.language,
    )
    db.add(row)
    db.commit()
    # Review finding 6: only a *successful* post counts against the cap --
    # recorded after the commit, not before the work is attempted.
    record_feedback_attempt(client_ip(request))
    return {"status": "recorded"}


def _feedback_summary(rows: list[Feedback]) -> FeedbackSummaryOut:
    questions: list[FeedbackQuestionStat] = []
    for key in ("q1", "q2", "q3"):
        values = [getattr(r, key) for r in rows]
        counts = {str(n): 0 for n in range(1, 6)}
        for v in values:
            counts[str(v)] += 1
        mean = round(sum(values) / len(values), 2) if values else None
        questions.append(FeedbackQuestionStat(key=key, mean=mean, counts=counts))

    comments = [
        FeedbackCommentOut(text=r.comment, created_at=r.created_at) for r in rows if r.comment
    ]
    return FeedbackSummaryOut(responses=len(rows), questions=questions, comments=comments)


def _session_feedback_rows(db: Session, session_id: str) -> list[Feedback]:
    """Review finding 2: a FIP's feedback (posted with only `fipId`, e.g.
    from the FIP editor rather than the session-level form) used to be
    invisible here because the query only matched `Feedback.session_id`.
    Include any feedback row whose `fip_id` belongs to one of this
    session's FIPs too."""
    fip_ids = [fid for (fid,) in db.query(Fip.id).filter(Fip.session_id == session_id).all()]
    condition = (
        or_(Feedback.session_id == session_id, Feedback.fip_id.in_(fip_ids))
        if fip_ids
        else Feedback.session_id == session_id
    )
    return db.query(Feedback).filter(condition).order_by(Feedback.created_at).all()


@router.get("/sessions/{session_id}/feedback", response_model=FeedbackSummaryOut)
def get_session_feedback(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> FeedbackSummaryOut:
    _get_owned_session(session_id, db, user)
    rows = _session_feedback_rows(db, session_id)
    return _feedback_summary(rows)


@router.get("/sessions/{session_id}/feedback.csv")
def get_session_feedback_csv(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Response:
    _get_owned_session(session_id, db, user)
    rows = _session_feedback_rows(db, session_id)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    _write_csv_row(writer, FEEDBACK_CSV_HEADER)
    for r in rows:
        _write_csv_row(
            writer, [r.session_id or "", _iso_utc(r.created_at), r.q1, r.q2, r.q3, r.comment or ""]
        )
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{session_id}-feedback.csv"'},
    )


@router.get("/fips/{fip_id}/feedback", response_model=FeedbackSummaryOut)
def get_fip_feedback(
    fip_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> FeedbackSummaryOut:
    """Review finding 2: the FIP owner (or admin) too can read the feedback
    posted against their own FIP directly, without needing to be the
    session's facilitator -- cheap to add alongside the session-level fix
    since it reuses `_feedback_summary`."""
    fip = db.get(Fip, fip_id)
    if fip is None or not can_write_owned(fip.owner_id, user):
        raise HTTPException(status_code=404, detail="not_found")
    rows = db.query(Feedback).filter(Feedback.fip_id == fip_id).order_by(Feedback.created_at).all()
    return _feedback_summary(rows)
