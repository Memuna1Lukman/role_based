from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from . import models


def is_admin(user: models.Users) -> bool:
    return user.role == models.UserRole.ADMIN


def get_project_or_404(db: Session, project_id: int) -> models.Project:
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project does not exist")
    return project


def get_task_or_404(db: Session, task_id: int) -> models.Task:
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def get_membership(db: Session, project_id: int, user_id: int):
    return db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id,
        models.ProjectMember.user_id == user_id
    ).first()


def require_member(db: Session, project_id: int, user: models.Users) -> None:
    """Any project member can pass. Global admins can always pass."""
    if is_admin(user):
        return
    if not get_membership(db, project_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def is_lead(db: Session, project_id: int, user: models.Users) -> bool:
    """True for global admins and for the project's PROJECT_LEAD members."""
    if is_admin(user):
        return True
    membership = get_membership(db, project_id, user.id)
    return membership is not None and membership.role == models.ProjectRole.PROJECT_LEAD


def require_lead(db: Session, project_id: int, user: models.Users) -> None:
    if not is_lead(db, project_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a project lead or admin can do this")