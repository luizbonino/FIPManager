"""POST /api/feedback and the two session feedback GET routes (spec
05-v1-completion.md §4). Anonymous by construction: no user_id, no IP, no
edit token stored -- the client IP is used only by the rate limiter and
discarded. CSRF applies to the POST like every other write (spec 01 §4, via
`fipm.auth.csrf_middleware`, already mounted for all non-GET /api/*)."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from fipm.auth import check_feedback_rate_limit
from fipm.authz import require_user
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
) -> dict[str, str]:
    settings = get_settings()
    if not settings.feedback_enabled:
        raise HTTPException(status_code=403, detail="feedback_disabled")
    check_feedback_rate_limit(request)

    if body.session_id is not None and db.get(WorkshopSession, body.session_id) is None:
        raise HTTPException(status_code=404, detail="not_found")
    if body.fip_id is not None and db.get(Fip, body.fip_id) is None:
        raise HTTPException(status_code=404, detail="not_found")

    row = Feedback(
        id=new_feedback_id(),
        session_id=body.session_id,
        fip_id=body.fip_id,
        q1=body.q1,
        q2=body.q2,
        q3=body.q3,
        comment=body.comment,
        language=body.language,
    )
    db.add(row)
    db.commit()
    return {"status": "recorded"}


@router.get("/sessions/{session_id}/feedback", response_model=FeedbackSummaryOut)
def get_session_feedback(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> FeedbackSummaryOut:
    _get_owned_session(session_id, db, user)
    rows = (
        db.query(Feedback)
        .filter(Feedback.session_id == session_id)
        .order_by(Feedback.created_at)
        .all()
    )

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


@router.get("/sessions/{session_id}/feedback.csv")
def get_session_feedback_csv(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> Response:
    _get_owned_session(session_id, db, user)
    rows = (
        db.query(Feedback)
        .filter(Feedback.session_id == session_id)
        .order_by(Feedback.created_at)
        .all()
    )

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
