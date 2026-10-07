from fastapi import HTTPException,Depends,status,APIRouter,Query
from typing import List,Optional
from .. import models,utils,schemas,oauth
from ..database import get_db
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

router = APIRouter(
    tags=["Users"],
    prefix="/users"
)

@router.post("/",status_code=status.HTTP_201_CREATED,response_model=schemas.UserResponse)
def create_new_user(user:schemas.UserInputs,db:Session = Depends(get_db)):
    user_model = user.model_dump()
    user_model["password_hash"] = utils.get_password_hash(user.password_hash)
    user_data = models.Users(**user_model)
    try:
        db.add(user_data)
        db.commit()
        db.refresh(user_data)
        return user_data
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="Registration failed. Email or Username is already taken.")


@router.get("/me",response_model=schemas.UserMe)
def get_me(db:Session = Depends(get_db),current_user:int = Depends(oauth.get_current_user)):
    query_user = db.query(models.Users).filter(
        models.Users.id == current_user.id
    ).first()
    if not query_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Not Found")
    return query_user


# --- RBAC: user management ---

# Any logged-in user: needed for assignee / add-member pickers
@router.get("/",response_model=List[schemas.UserResponse])
def get_all_users(
    search:Optional[str] = None,
    limit:int = Query(50,le=100),
    skip:int = 0,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    query = db.query(models.Users)
    if search:
        query = query.filter(or_(
            models.Users.email.ilike(f"%{search}%"),
            models.Users.full_name.ilike(f"%{search}%")
        ))
    return query.order_by(models.Users.full_name).offset(skip).limit(limit).all()


# Admin only
@router.patch("/{user_id}/role",response_model=schemas.UserResponse)
def update_user_role(
    user_id:int,
    payload:schemas.UserRoleUpdate,
    db:Session = Depends(get_db),
    admin:models.Users = Depends(oauth.require_admin)):
    # stops the last admin from locking everyone out
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="You cannot change your own role")

    target_user = db.query(models.Users).filter(models.Users.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")

    target_user.role = payload.role
    db.commit()
    db.refresh(target_user)
    return target_user


# Admin only
@router.patch("/{user_id}/active",response_model=schemas.UserResponse)
def update_user_active(
    user_id:int,
    payload:schemas.UserActiveUpdate,
    db:Session = Depends(get_db),
    admin:models.Users = Depends(oauth.require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="You cannot deactivate yourself")

    target_user = db.query(models.Users).filter(models.Users.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")

    target_user.is_active = payload.is_active
    # later: when you add RefreshToken, revoke this user's sessions here if is_active is False
    db.commit()
    db.refresh(target_user)
    return target_user