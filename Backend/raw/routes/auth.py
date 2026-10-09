import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, oauth, utils
from ..config import settings
from ..database import get_db

router = APIRouter(tags=["Authentication"], prefix="/auth")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie("access_token", f"Bearer {access_token}", max_age=settings.access_token_expire_minutes * 60, **common)
    response.set_cookie("refresh_token", refresh_token, max_age=settings.refresh_token_expire_days * 86400, **common)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def issue_session(db: Session, user: models.Users, request: Request, family_id: str | None = None) -> tuple[str, str]:
    refresh_token = secrets.token_urlsafe(48)
    db.add(models.RefreshToken(
        user_id=user.id, token_hash=token_hash(refresh_token), family_id=family_id or str(uuid.uuid4()),
        user_agent=request.headers.get("user-agent"), ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    ))
    return oauth.create_token({"owner_id": user.id}), refresh_token


@router.post("/login")
def login_user(response: Response, request: Request, credentials: OAuth2PasswordRequestForm = Depends(),
               db: Session = Depends(get_db)):
    user = db.query(models.Users).filter(models.Users.email == credentials.username).first()
    if not user or not user.is_active or not utils.verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    access_token, refresh_token = issue_session(db, user, request)
    db.commit()
    set_auth_cookies(response, access_token, refresh_token)
    return {"message": "Login successful"}


@router.post("/refresh")
def refresh_tokens(response: Response, request: Request, db: Session = Depends(get_db)):
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please sign in again.")
    stored = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash(raw_token)).first()
    now = datetime.now(timezone.utc)
    if not stored or stored.revoked_at or stored.expires_at <= now or not stored.user.is_active:
        if stored and stored.revoked_at:
            db.query(models.RefreshToken).filter(models.RefreshToken.family_id == stored.family_id,
                                                 models.RefreshToken.revoked_at.is_(None)).update({"revoked_at": now})
            db.commit()
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please sign in again.")
    stored.revoked_at = now
    access_token, refresh_token = issue_session(db, stored.user, request, stored.family_id)
    db.flush()
    replacement = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash(refresh_token)).one()
    stored.replaced_by_id = replacement.id
    db.commit()
    set_auth_cookies(response, access_token, refresh_token)
    return {"message": "Session refreshed"}


@router.post("/logout")
def logout_user(response: Response, request: Request, db: Session = Depends(get_db)):
    raw_token = request.cookies.get("refresh_token")
    if raw_token:
        db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash(raw_token),
                                             models.RefreshToken.revoked_at.is_(None)).update({"revoked_at": datetime.now(timezone.utc)})
        db.commit()
    clear_auth_cookies(response)
    return {"message": "Logout successful"}


@router.post("/logout-all")
def logout_all(response: Response, db: Session = Depends(get_db),
               current_user: models.Users = Depends(oauth.get_current_user)):
    db.query(models.RefreshToken).filter(models.RefreshToken.user_id == current_user.id,
                                         models.RefreshToken.revoked_at.is_(None)).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()
    clear_auth_cookies(response)
    return {"message": "Logged out of all devices"}
