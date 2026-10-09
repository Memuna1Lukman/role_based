from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models, schemas
from .config import settings
from .database import get_db

oauth2_scheme = APIKeyCookie(name="access_token", auto_error=False)


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_token(token: str, credential_exception: HTTPException) -> schemas.TokenData:
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("owner_id")
        if user_id is None:
            raise credential_exception
        return schemas.TokenData(id=int(user_id))
    except (JWTError, ValueError):
        raise credential_exception


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Users:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please sign in to continue.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    token_data = verify_token(token, credentials_exception)
    user = db.query(models.Users).filter(models.Users.id == token_data.id).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_admin(current_user: models.Users = Depends(get_current_user)) -> models.Users:
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user
