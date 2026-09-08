from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from fipm.auth import (
    COOKIE_NAME,
    check_login_rate_limit,
    check_register_rate_limit,
    clear_session_cookie,
    create_auth_session,
    dummy_verify,
    hash_password,
    needs_rehash,
    record_login_failure,
    revoke_all_sessions,
    set_session_cookie,
    verify_password,
)
from fipm.authz import require_user
from fipm.config import get_settings
from fipm.db import get_db
from fipm.ids import hash_token, new_user_id
from fipm.models import AuthSession, Fer, Fip, KnowledgeModel, User, WorkshopSession
from fipm.schemas import (
    DeleteAccountRequest,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    settings = get_settings()
    if not settings.registration_open:
        raise HTTPException(status_code=403, detail="registration_closed")
    check_register_rate_limit(request)

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
    )
    db.add(user)
    db.commit()
    db.refresh(user)

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


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(require_user)) -> UserOut:
    return UserOut.model_validate(user)


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
    db.commit()

    # Revoke every other session, keeping the one used for this request alive.
    current_token = request.cookies.get(COOKIE_NAME)
    current_hash = hash_token(current_token) if current_token else None
    stmt = delete(AuthSession).where(AuthSession.user_id == user.id)
    if current_hash:
        stmt = stmt.where(AuthSession.id != current_hash)
    db.execute(stmt)
    db.commit()


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
    # account; published ones are shared artifacts and are anonymised instead.
    db.query(KnowledgeModel).filter(
        KnowledgeModel.owner_id == user.id, KnowledgeModel.status == "draft"
    ).delete(synchronize_session=False)
    db.query(KnowledgeModel).filter(
        KnowledgeModel.owner_id == user.id, KnowledgeModel.status != "draft"
    ).update({"owner_id": None})
    # FIPs are anonymised and forced to "link" visibility: a "private" FIP
    # with no owner would otherwise become unreadable by anyone at all.
    db.query(Fip).filter(Fip.owner_id == user.id).update({"owner_id": None, "visibility": "link"})

    revoke_all_sessions(db, user.id)
    db.delete(user)
    db.commit()
    clear_session_cookie(response, settings)
