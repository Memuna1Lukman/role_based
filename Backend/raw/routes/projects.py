from fastapi import APIRouter,HTTPException,status,Depends,Response,Query
from .. import models,schemas,oauth2,rbac,activity
from ..database  import get_db
from sqlalchemy.orm import Session
from typing import List,Optional


router = APIRouter(
    tags=["Tasks"]
)


def check_assignee(db:Session,project_id:int,assignee_id:Optional[int]):
    # an assignee must be a member of the same project
    if assignee_id is not None and not rbac.get_membership(db,project_id,assignee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned user is not a member of this project",
        )


# Any project member (or admin) can view tasks
@router.get("/projects/{project_id}/tasks",response_model=List[schemas.TaskResponse])
def get_tasks(
    project_id:int,
    status_filter:Optional[models.TaskStatus] = Query(None,alias="status"),
    assignee_id:Optional[int] = None,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth2.get_current_user)):
    rbac.get_project_or_404(db,project_id)
    rbac.require_member(db,project_id,current_user)

    query = db.query(models.Task).filter(models.Task.project_id == project_id)
    if status_filter:
        query = query.filter(models.Task.status == status_filter)
    if assignee_id:
        query = query.filter(models.Task.assignee_id == assignee_id)
    return query.order_by(models.Task.created_at.desc()).all()


# Only a project lead (or admin) can create tasks
@router.post("/projects/{project_id}/tasks",status_code=status.HTTP_201_CREATED,response_model=schemas.TaskResponse)
def create_task(
    task:schemas.CreateTasks,
    project_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth2.get_current_user)):
    rbac.get_project_or_404(db,project_id)
    rbac.require_lead(db,project_id,current_user)
    check_assignee(db,project_id,task.assignee_id)

    new_task = models.Task(**task.model_dump(),project_id=project_id,created_by_id=current_user.id)
    db.add(new_task)
    db.flush()  # gives new_task an id without committing yet

    activity.record_event(
        db,project_id,current_user.id,"task.created","task",new_task.id,
        {"title":new_task.title,"assignee_id":new_task.assignee_id}
    )
    activity.notify(
        db,new_task.assignee_id,current_user.id,models.NotificationType.TASK_ASSIGNED,
        title="New task assigned to you",message=new_task.title,link=f"/tasks/{new_task.id}",
        payload={"task_id":new_task.id,"project_id":project_id}
    )

    db.commit()
    db.refresh(new_task)
    return new_task


@router.get("/tasks/{task_id}",response_model=schemas.TaskResponse)
def get_one_task(
    task_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth2.get_current_user)):
    task = rbac.get_task_or_404(db,task_id)
    rbac.require_member(db,task.project_id,current_user)
    return task


# Lead/admin: can edit every field.
# Assigned member: can only change the status of their own task.
@router.patch("/tasks/{task_id}",response_model=schemas.TaskResponse)
def edit_task(
    task_id:int,
    payload:schemas.TaskUpdate,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth2.get_current_user)):
    task = rbac.get_task_or_404(db,task_id)
    rbac.require_member(db,task.project_id,current_user)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return task

    # title and status cannot be set to null
    for field in ("title","status"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f"{field} cannot be empty")

    if rbac.is_lead(db,task.project_id,current_user):
        pass
    elif task.assignee_id == current_user.id:
        if set(changes) - {"status"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Members can only update the status of tasks assigned to them"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Members can only update tasks assigned to them"
        )

    if "assignee_id" in changes:
        check_assignee(db,task.project_id,changes["assignee_id"])

    old_status = task.status
    old_assignee = task.assignee_id

    for key,value in changes.items():
        setattr(task,key,value)

    link = f"/tasks/{task.id}"

    if task.status != old_status:
        activity.record_event(
            db,task.project_id,current_user.id,"task.status_changed","task",task.id,
            {"title":task.title,"from":old_status.value,"to":task.status.value}
        )
        # tell the assignee and the creator (notify() skips the person who made the change)
        for recipient_id in {task.assignee_id,task.created_by_id}:
            activity.notify(
                db,recipient_id,current_user.id,models.NotificationType.TASK_STATUS_CHANGED,
                title="Task status changed",message=f"{task.title}: {old_status.value} → {task.status.value}",
                link=link,payload={"task_id":task.id,"project_id":task.project_id}
            )

    if task.assignee_id != old_assignee:
        activity.record_event(
            db,task.project_id,current_user.id,"task.assigned","task",task.id,
            {"title":task.title,"from":old_assignee,"to":task.assignee_id}
        )
        activity.notify(
            db,task.assignee_id,current_user.id,models.NotificationType.TASK_ASSIGNED,
            title="New task assigned to you",message=task.title,link=link,
            payload={"task_id":task.id,"project_id":task.project_id}
        )

    other_fields = set(changes) - {"status","assignee_id"}
    if other_fields:
        activity.record_event(
            db,task.project_id,current_user.id,"task.updated","task",task.id,
            {"title":task.title,"fields":sorted(other_fields)}
        )

    db.commit()
    db.refresh(task)
    return task


# Only a project lead (or admin) can delete tasks
@router.delete("/tasks/{task_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth2.get_current_user)):
    task = rbac.get_task_or_404(db,task_id)
    rbac.require_lead(db,task.project_id,current_user)

    activity.record_event(
        db,task.project_id,current_user.id,"task.deleted","task",task.id,
        {"title":task.title}
    )
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)