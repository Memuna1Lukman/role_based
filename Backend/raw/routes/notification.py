from datetime import datetime, timezone
from fastapi import APIRouter,Depends, HTTPException, Query, Response,status
from sqlalchemy.orm  import Session
from .. import models,schemas,oauth,rbac,activity
from ..database import get_db
from typing import List, Optional


router = APIRouter(
    tags=["Notification"],
    prefix="/notify"
)


router.get("",response_model=List[schemas.NotifyOut])
def get_notifications(
    unread:bool = False,
    limit:int = Query(20,ge=1,le=100),
    before_id:Optional[int] = None,
    db:Session=Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    query = db.query(models.Notification).filter(models.Notification.user_id == current_user.id)
    if unread:
        query = query.filter(models.Notification.is_read == False)
    if before_id:
        query = query.filter(models.Notification.id < before_id)
    return query.order_by(models.Notification.id.desc()).limit(limit).all()


def get_own_notification_or_404(db:Session,notification_id:int,user_id:int) -> models.Notification:
    # filtering by user_id means other people's notifications look like they don't exist
    notification = db.query(models.Notification).filter(
        models.Notification.id == notification_id,
        models.Notification.user_id == user_id
    ).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Notification not found")
    return notification

@router.get("/unread-count")
def get_unread_count(
    db:Session=Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    count = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False
    ).count()
    return {"count": count}


@router.patch("/{notification_id}/read",response_model=schemas.NotifyOut)
def mark_as_read(
    notification_id:int,
    db:Session=Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    notification = get_own_notification_or_404(db,notification_id,current_user.id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return notification
 
 
@router.post("/read-all")
def mark_all_as_read(
    db:Session=Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    updated = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False
    ).update({"is_read": True, "read_at": datetime.now(timezone.utc)})
    db.commit()
    return {"updated": updated}
 
 
@router.delete("/{notification_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id:int,
    db:Session=Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    notification = get_own_notification_or_404(db,notification_id,current_user.id)
    db.delete(notification)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)