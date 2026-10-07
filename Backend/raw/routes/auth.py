from fastapi import HTTPException,Depends,status,APIRouter,Response
from .. import models,utils,schemas,oauth
from ..database import get_db
from sqlalchemy.orm import Session
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from ..config import settings
from datetime import datetime, timezone

router = APIRouter(
    tags= ["Authentication"],
    prefix="/auth"
)

@router.post("/login")
def login_user(
    response:Response,
    user:OAuth2PasswordRequestForm=Depends(),db:Session = Depends(get_db)):
    check_user = db.query(models.Users).filter(models.Users.email == user.username).first()
    if not check_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail=f"Invalid Credentials")

    verify_password = utils.unhash_password(user.password,check_user.password_hash)
    if not verify_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail=f"Invalid Credentials")

    
    access_token = oauth.create_token(data={"owner_id": check_user.id})
    # reponse in the cookie form
    response.set_cookie(
        key="access_token",
        value = f"Bearer {access_token}",
        httponly= True,
        secure = False,
        samesite="lax",
        max_age=settings.access_token_expire_minutes*60
    )

    return {"message": "Login successful"}   



@router.post("/")
def logout_user (
    response:Response
):
    response.set_cookie(
        key="access_token",
        value = "",
        httponly= True,
        secure = False,
        samesite="lax",
        max_age=0
        )
    
    return {"message": "Logout successful"}


# NOTE: the router prefix is already "/auth", so the path here is just "/refresh"
@router.post("/refresh")
def refresh_tokens():
    # This must NOT depend on get_current_user: refresh is called when the access
    # token has expired, so that dependency would always reject the request.
    # It will read a refresh-token cookie instead, once login issues one.
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED,detail="Not implemented yet")


# Logs the CURRENT user out of every device (not an admin-only action)
@router.post("/logout-all")
def logout_all(
    response:Response,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth2.get_current_user)):
    # revoke every active refresh token this user has
    db.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == current_user.id,
        models.RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()

    # clear the cookie on this device too
    response.set_cookie(
        key="access_token",
        value = "",
        httponly= True,
        secure = False,
        samesite="lax",
        max_age=0
        )

    return {"message": "Logged out of all devices"}