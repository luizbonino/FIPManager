from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from fipm.auth import (
    COOKIE_NAME,
    check_login_rate_limit,
    check_register_rate_limit,
    check_resend_rate_limit,
    clear_session_cookie,
    create_auth_session,
    dummy_verify,
    hash_password,
    invalidate_password_reset_tokens,
    issue_email_token,
    needs_rehash,
    password_reset_over_limit,
    record_login_failure,
    record_password_reset_attempt,
    record_resend_attempt,
    resolve_email_token,
    revoke_all_sessions,
    set_session_cookie,
    verify_password,
)
from fipm.authz import require_user
from fipm.config import get_settings
from fipm.db import SessionLocal, get_db
from fipm.ids import hash_token, new_user_id
from fipm.mail import queue_mail, render_mail, send_mail
from fipm.models import AuthSession, Fer, Fip, KnowledgeModel, User, WorkshopSession
from fipm.privacy import current_privacy_version
from fipm.schemas import (
    DeleteAccountRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    RegisterRequest,
    UserOut,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# spec 07-mail-and-migration.md §1: `{appName}` placeholder for every
# rendered mail template.
APP_NAME = "FIP Manager"


def _mail_link(settings, path: str, token: str) -> str:
    return f"{settings.base_url}{path}?token={token}"


def _queue_verify_email_mail(
    background_tasks: BackgroundTasks, db: Session, settings, user: User
) -> None:
    token = issue_email_token(db, user, "verify_email", user.email, settings.mail_token_ttl_hours)
    link = _mail_link(settings, "/verify", token)
    subject, text = render_mail(
        "verify-email",
        user.language,
        {
            "appName": APP_NAME,
            "displayName": user.display_name,
            "link": link,
            "baseUrl": settings.base_url,
            "expiresHours": str(settings.mail_token_ttl_hours),
        },
    )
    queue_mail(background_tasks, user.email, subject, text)


def _queue_password_changed_mail(background_tasks: BackgroundTasks, settings, user: User) -> None:
    """spec 07 §1: sent after a self-service reset confirm and after an
    admin reset-password (routers/admin.py)."""
    subject, text = render_mail(
        "password-changed",
        user.language,
        {
            "appName": APP_NAME,
            "displayName": user.display_name,
            "baseUrl": settings.base_url,
            "contactEmail": settings.contact_email,
            "expiresHours": "0",
        },
    )
    queue_mail(background_tasks, user.email, subject, text)


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> UserOut:
    settings = get_settings()
    if not settings.registration_open:
        raise HTTPException(status_code=403, detail="registration_closed")
    check_register_rate_limit(request)

    # spec 05-v1-completion.md §2: a value that doesn't match the current
    # privacy notice version is a stale tab, not a client bug -- 400 so the
    # frontend re-fetches GET /api/privacy and re-asks, rather than the
    # generic 422 pydantic already gives for a missing field.
    current_version = current_privacy_version(settings)
    if body.privacy_accepted_version != current_version:
        raise HTTPException(status_code=400, detail="privacy_version_mismatch")

    email = body.email.strip().lower()
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email_taken")

    user = User(
        id=new_user_id(),
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="user",
        language=body.language or settings.default_language,
        privacy_accepted_version=body.privacy_accepted_version,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # spec 07-mail-and-migration.md §2: after the user row commits, issue a
    # verify_email token and queue the mail; the response is unchanged
    # (201 + cookie).
    _queue_verify_email_mail(background_tasks, db, settings, user)

    _, token = create_auth_session(db, user, settings)
    set_session_cookie(response, token, settings)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    settings = get_settings()
    email = body.email.strip().lower()
    check_login_rate_limit(request, email)

    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        dummy_verify()
        record_login_failure(request, email)
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if not verify_password(user.password_hash, body.password):
        record_login_failure(request, email)
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()

    _, token = create_auth_session(db, user, settings)
    set_session_cookie(response, token, settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    settings = get_settings()
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.id == hash_token(token)))
        db.commit()
    clear_session_cookie(response, settings)


@router.get("/me")
def get_me(user: User = Depends(require_user)) -> dict:
    """`UserOut` plus `verificationRequired` (spec 07 §2): the
    `FIPM_REQUIRE_EMAIL_VERIFICATION` setting, a sibling field so the SPA
    knows whether to nag an unverified account -- not per-user state."""
    settings = get_settings()
    data = UserOut.model_validate(user).model_dump(mode="json", by_alias=True)
    data["verificationRequired"] = settings.require_email_verification
    return data


@router.post("/verify-email", response_model=UserOut)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)) -> UserOut:
    """spec 07 §2: no auth -- the token is the credential. Success sets
    `email_verified_at`/`used_at`; a replay of the same token is 400
    `invalid_token` by design (already used)."""
    _row, user = resolve_email_token(db, body.token, "verify_email")
    # `resolve_email_token` already claimed and committed `row.used_at`
    # (audit finding 9); only `user.email_verified_at` remains to set here.
    user.email_verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/verify-email/resend", status_code=202)
def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    """spec 07 §2: 202 always, even when already verified (no state leak,
    no mail then). 3/hour per user id, 10/hour per client ip -> 429 with
    Retry-After."""
    check_resend_rate_limit(request, user.id)
    record_resend_attempt(request, user.id)
    if user.email_verified_at is None:
        settings = get_settings()
        _queue_verify_email_mail(background_tasks, db, settings, user)
    return None


def _issue_password_reset_and_mail(email: str) -> None:
    """Runs inside a `BackgroundTasks` callback, after the 202 has already
    gone out (audit finding 10). Previously `request_password_reset` did
    the user lookup *and*, only on a match, the `issue_email_token`
    DELETE+INSERT and `render_mail` template work synchronously before
    responding -- so a known email took measurably longer to answer than
    an unknown one, exactly the timing oracle spec §3's "byte-identical
    either way" is meant to close. Doing every bit of match-dependent work
    here instead (with its own DB session, since the request's `db` session
    closes once the response is sent) makes the synchronous path -- rate
    limit check, then schedule this task -- identical regardless of
    whether the address exists. A failure here (unknown email: nothing to
    do; DB or mail error: logged) never surfaces to the client, which
    already got its 202."""
    try:
        settings = get_settings()
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).one_or_none()
            if user is None:
                return
            recipient = user.email
            token = issue_email_token(
                db, user, "password_reset", user.email, settings.reset_token_ttl_hours
            )
            link = _mail_link(settings, "/reset-password", token)
            subject, text = render_mail(
                "password-reset",
                user.language,
                {
                    "appName": APP_NAME,
                    "displayName": user.display_name,
                    "link": link,
                    "baseUrl": settings.base_url,
                    "expiresHours": str(settings.reset_token_ttl_hours),
                },
            )
        # `db` (and with it, `user`) is closed at this point -- `recipient`
        # was captured beforehand so sending doesn't touch the ORM object.
        send_mail(recipient, subject, text)
    except Exception:
        # spec §1: mail (and, here, the token issuance behind it) must never
        # turn the already-sent 202 into a client-visible failure.
        logger.exception("password-reset background task failed for %s", email)


@router.post("/password-reset/request", status_code=202)
def request_password_reset(
    body: PasswordResetRequestRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> None:
    """spec 07 §3: always 202, empty body, whether the address exists, is
    malformed or is already mid-reset -- byte-identical either way. Rate
    limit 3/hour per lowercased email, 10/hour per ip; over-limit also
    returns 202 (a 429 keyed on an email is itself an enumeration oracle)
    and the mail is dropped and logged. The user lookup and, only on a
    match, the password_reset token issuance and mail are deferred to a
    background task (`_issue_password_reset_and_mail`, audit finding 10) so
    the synchronous response path can't leak whether the address exists."""
    email = body.email.strip().lower()
    over_limit = password_reset_over_limit(request, email)
    record_password_reset_attempt(request, email)
    if over_limit:
        logger.info("password-reset request for %s over rate limit; mail dropped", email)
        return None
    background_tasks.add_task(_issue_password_reset_and_mail, email)
    return None


@router.post("/password-reset/confirm", status_code=204)
def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> None:
    """spec 07 §3, one transaction: argon2id rehash, `used_at` set (already
    done atomically by `resolve_email_token`, audit finding 9), every
    `auth_sessions` row of that user deleted (the caller's too), and
    `email_verified_at` set if it was null (completing a reset proves
    control of the mailbox). Also (audit findings 7/8): every other
    outstanding `password_reset` token for this user is invalidated -- a
    second still-unused reset link must not keep working once one has been
    consumed -- and `must_change_password` is cleared, the same as a
    self-service `/auth/password` change does, since a completed reset is
    just another way of setting a fresh password. A password-changed
    notice is queued afterwards (spec §1)."""
    _row, user = resolve_email_token(db, body.token, "password_reset")
    now = datetime.now(UTC)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    if user.email_verified_at is None:
        user.email_verified_at = now
    db.commit()
    revoke_all_sessions(db, user.id)
    invalidate_password_reset_tokens(db, user.id)

    settings = get_settings()
    _queue_password_changed_mail(background_tasks, settings, user)
    return None


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    user.password_hash = hash_password(body.new_password)
    # spec 05-v1-completion.md §1: a successful password change clears the
    # flag an admin reset-password sets, so the next request stops getting
    # 403 password_change_required.
    user.must_change_password = False
    db.commit()

    # Revoke every other session, keeping the one used for this request alive.
    current_token = request.cookies.get(COOKIE_NAME)
    current_hash = hash_token(current_token) if current_token else None
    stmt = delete(AuthSession).where(AuthSession.user_id == user.id)
    if current_hash:
        stmt = stmt.where(AuthSession.id != current_hash)
    db.execute(stmt)
    db.commit()

    # Audit finding 7: an outstanding, still-unused password_reset link
    # must not survive a password change made this way -- otherwise a
    # stale reset email (the user's own, or one an attacker triggered)
    # would still work after the user thinks they've locked things down.
    invalidate_password_reset_tokens(db, user.id)


@router.delete("/me", status_code=204)
def delete_me(
    body: DeleteAccountRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    settings = get_settings()
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    # Sessions the user facilitated: close and anonymise rather than cascade
    # (their FIPs and edit tokens must keep working for anonymous holders).
    db.query(WorkshopSession).filter(WorkshopSession.owner_id == user.id).update(
        {"owner_id": None, "status": "closed"}
    )
    # User-contributed FERs stay (they may be referenced by other FIPs); only
    # the ownership link is cleared.
    db.query(Fer).filter(Fer.owner_id == user.id).update({"owner_id": None})
    # Draft knowledge models are the user's own scratch work and go with the
    # account; published ones are shared artifacts and are anonymised instead
    # -- spec 04-knowledge-model-editor.md §1: owner_id=NULL, visibility=
    # "public", so every FIP that references them keeps resolving and they
    # become read-only community content.
    # NOTE: KnowledgeModel.owner_id has no ondelete on the Fip FK, so any KM
    # authoring endpoint that deletes a KM referenced by FIPs must reassign
    # or refuse rather than delete it, same as here.
    db.query(KnowledgeModel).filter(
        KnowledgeModel.owner_id == user.id, KnowledgeModel.status == "draft"
    ).delete(synchronize_session=False)
    db.query(KnowledgeModel).filter(
        KnowledgeModel.owner_id == user.id, KnowledgeModel.status != "draft"
    ).update({"owner_id": None, "visibility": "public"})
    # FIPs (review finding 3): a private FIP with no session would become
    # unreadable by anyone once ownerless, so it is deleted outright. A
    # private FIP tied to a workshop session must stay reachable by the
    # session owner/room, so it is anonymised and downgraded to "link"
    # instead. Non-private FIPs keep their existing visibility and are
    # simply anonymised.
    db.query(Fip).filter(
        Fip.owner_id == user.id, Fip.visibility == "private", Fip.session_id.is_(None)
    ).delete(synchronize_session=False)
    db.query(Fip).filter(
        Fip.owner_id == user.id, Fip.visibility == "private", Fip.session_id.isnot(None)
    ).update({"owner_id": None, "visibility": "link"})
    db.query(Fip).filter(Fip.owner_id == user.id, Fip.visibility != "private").update(
        {"owner_id": None}
    )

    revoke_all_sessions(db, user.id)
    db.delete(user)
    db.commit()
    clear_session_cookie(response, settings)
