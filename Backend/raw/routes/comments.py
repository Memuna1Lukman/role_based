from fastapi import APIRouter,Depends,status
from sqlalchemy.orm  import Session
from .. import models,schemas,oauth,rbac,activity
from ..database import get_db
from typing import List


router = APIRouter(tags=["Comments"], prefix="/tasks/{task_id}/comments")


# "" instead of "/" so /tasks/1/comments works without a trailing-slash redirect
@router.get("",response_model=List[schemas.CommentOut])
def get_comments(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(oauth.get_current_user)):
    task = rbac.get_task_or_404(db,task_id)
    rbac.require_member(db,task.project_id,current_user)

    return (
        db.query(models.Comment)
        .filter(models.Comment.task_id == task_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )


@router.post("",response_model=schemas.CommentOut, status_code=status.HTTP_201_CREATED)
def create_comment(
    comment: schemas.CommentCreate,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(oauth.get_current_user)):
    task = rbac.get_task_or_404(db,task_id)
    rbac.require_member(db,task.project_id,current_user)

    new_comment = models.Comment(
        task_id=task_id,
        author_id=current_user.id,
        body=comment.body,
    )
    db.add(new_comment)
    db.flush()

    activity.record_event(
        db,task.project_id,current_user.id,"comment.created","comment",new_comment.id,
        {"task_id":task.id,"task_title":task.title}
    )
    # tell the assignee and the creator (notify() skips the commenter)
    for recipient_id in {task.assignee_id,task.created_by_id}:
        activity.notify(
            db,recipient_id,current_user.id,models.NotificationType.TASK_COMMENTED,
            title="New comment on a task",message=comment.body[:100],link=f"/tasks/{task.id}",
            payload={"task_id":task.id,"comment_id":new_comment.id}
        )

    db.commit()
    db.refresh(new_comment)
    return new_comment