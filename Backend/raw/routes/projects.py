from fastapi import APIRouter,Depends,status,HTTPException,Response
from sqlalchemy.orm  import Session
from .. import models,schemas,oauth,rbac,activity
from ..database import get_db
from typing import List

router = APIRouter(
    tags=["Projects"]
)


def count_leads(db:Session,project_id:int) -> int:
    return db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id,
        models.ProjectMember.role == models.ProjectRole.PROJECT_LEAD
    ).count()
 
 
def get_member_or_404(db:Session,project_id:int,user_id:int) -> models.ProjectMember:
    member = rbac.get_membership(db,project_id,user_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User is not a member of this project")
    return member

@router.get("/",response_model=List[schemas.ProjectResponse])
def get_projects(
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    query = db.query(models.Project)
    if not rbac.is_admin(current_user):
        query = query.join(
            models.ProjectMember,models.ProjectMember.project_id == models.Project.id
        ).filter(models.ProjectMember.user_id == current_user.id)
    return query.order_by(models.Project.created_at.desc()).all()
 
 
# Admin only. The creator automatically becomes the project lead.
@router.post("/",status_code=status.HTTP_201_CREATED,response_model=schemas.ProjectResponse)
def create_project(
    project:schemas.ProjectCreate,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    if not rbac.is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Admin access required")
 
    new_project = models.Project(**project.model_dump(),created_by_id=current_user.id)
    db.add(new_project)
    db.flush()  # gives new_project an id without committing yet
 
    db.add(models.ProjectMember(
        project_id=new_project.id,
        user_id=current_user.id,
        role=models.ProjectRole.PROJECT_LEAD
    ))
    activity.record_event(
        db,new_project.id,current_user.id,"project.created","project",new_project.id,
        {"name":new_project.name}
    )
 
    activity.commit(db)
    db.refresh(new_project)
    return new_project
 
 
@router.get("/{project_id}",response_model=schemas.ProjectResponse)
def get_one_project(
    project_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    project = rbac.get_project_or_404(db,project_id)
    rbac.require_member(db,project_id,current_user)
    return project
 
 
@router.patch("/{project_id}",response_model=schemas.ProjectResponse)
def edit_project(
    project_id:int,
    payload:schemas.ProjectUpdate,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    project = rbac.get_project_or_404(db,project_id)
    rbac.require_lead(db,project_id,current_user)
 
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return project
    if "name" in changes and not changes["name"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="name cannot be empty")
 
    for key,value in changes.items():
        setattr(project,key,value)
 
    activity.record_event(
        db,project_id,current_user.id,"project.updated","project",project_id,
        {"name":project.name,"fields":sorted(changes)}
    )
 
    activity.commit(db)
    db.refresh(project)
    return project
 
 
# Admin only. Members, tasks and comments are deleted with it.
@router.delete("/{project_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    project = rbac.get_project_or_404(db,project_id)
    if not rbac.is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Admin access required")
 
    db.delete(project)
    activity.commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.get("/{project_id}/members",response_model=List[schemas.ProjectMemberResponse])
def get_members(
    project_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    rbac.get_project_or_404(db,project_id)
    rbac.require_member(db,project_id,current_user)
 
    return db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id
    ).order_by(models.ProjectMember.joined_at.asc()).all()
 
 
@router.post("/{project_id}/members",status_code=status.HTTP_201_CREATED,response_model=schemas.ProjectMemberResponse)
def add_member(
    project_id:int,
    payload:schemas.ProjectMemberAdd,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    project = rbac.get_project_or_404(db,project_id)
    rbac.require_lead(db,project_id,current_user)
 
    user = db.query(models.Users).filter(models.Users.id == payload.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    if rbac.get_membership(db,project_id,payload.user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="User is already a member of this project")
 
    new_member = models.ProjectMember(project_id=project_id,user_id=payload.user_id,role=payload.role)
    db.add(new_member)
    db.flush()
 
    activity.record_event(
        db,project_id,current_user.id,"member.added","member",payload.user_id,
        {"user_id":payload.user_id,"full_name":user.full_name,"role":payload.role.value}
    )
    activity.notify(
        db,payload.user_id,current_user.id,models.NotificationType.ADDED_TO_PROJECT,
        title="You were added to a project",message=project.name,link=f"/projects/{project_id}",
        payload={"project_id":project_id,"role":payload.role.value}
    )
 
    activity.commit(db)
    db.refresh(new_member)
    return new_member
 
 
# Change a member's project role (promote to lead / demote to member)
@router.patch("/{project_id}/members/{user_id}",response_model=schemas.ProjectMemberResponse)
def change_member_role(
    project_id:int,
    user_id:int,
    payload:schemas.ProjectMemberRoleUpdate,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    project = rbac.get_project_or_404(db,project_id)
    rbac.require_lead(db,project_id,current_user)
    member = get_member_or_404(db,project_id,user_id)
 
    if member.role == payload.role:
        return member
 
    # a project must always keep at least one lead
    if member.role == models.ProjectRole.PROJECT_LEAD and count_leads(db,project_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A project must have at least one lead. Promote someone else first."
        )
 
    old_role = member.role
    member.role = payload.role
 
    activity.record_event(
        db,project_id,current_user.id,"member.role_changed","member",user_id,
        {"user_id":user_id,"from":old_role.value,"to":payload.role.value}
    )
    activity.notify(
        db,user_id,current_user.id,models.NotificationType.ROLE_CHANGED,
        title="Your project role changed",message=f"{project.name}: {old_role.value} → {payload.role.value}",
        link=f"/projects/{project_id}",payload={"project_id":project_id,"role":payload.role.value}
    )
 
    activity.commit(db)
    db.refresh(member)
    return member
 
 
# A lead/admin can remove anyone. A member can remove themselves (leave).
@router.delete("/{project_id}/members/{user_id}",status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id:int,
    user_id:int,
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    project = rbac.get_project_or_404(db,project_id)
    if user_id != current_user.id:
        rbac.require_lead(db,project_id,current_user)
    member = get_member_or_404(db,project_id,user_id)
 
    if member.role == models.ProjectRole.PROJECT_LEAD and count_leads(db,project_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The last lead cannot be removed. Promote someone else first."
        )
 
    # their tasks in this project become unassigned
    db.query(models.Task).filter(
        models.Task.project_id == project_id,
        models.Task.assignee_id == user_id
    ).update({"assignee_id": None})
 
    activity.record_event(
        db,project_id,current_user.id,"member.removed","member",user_id,
        {"user_id":user_id,"left":user_id == current_user.id}
    )
    activity.notify(
        db,user_id,current_user.id,models.NotificationType.REMOVED_FROM_PROJECT,
        title="You were removed from a project",message=project.name,
        payload={"project_id":project_id}
    )
 
    db.delete(member)
    activity.commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
