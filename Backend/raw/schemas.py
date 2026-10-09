from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import NotificationType, ProjectRole, TaskStatus, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserBrief(ORMModel):
    id: int
    full_name: str
    avatar_url: Optional[str] = None


class UserInputs(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    avatar_url: Optional[str] = None


class UserResponse(UserBrief):
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class UserMe(UserResponse):
    pass


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserActiveUpdate(BaseModel):
    is_active: bool


class TokenData(BaseModel):
    id: Optional[int] = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class ProjectResponse(ORMModel):
    id: int
    name: str
    description: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ProjectMemberAdd(BaseModel):
    user_id: int
    role: ProjectRole = ProjectRole.MEMBER


class ProjectMemberRoleUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberResponse(ORMModel):
    id: int
    project_id: int
    user_id: int
    role: ProjectRole
    joined_at: datetime


class CreateTasks(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.TODO
    assignee_id: Optional[int] = None
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    assignee_id: Optional[int] = None
    due_date: Optional[datetime] = None


class TaskResponse(ORMModel):
    id: int
    project_id: int
    title: str
    description: Optional[str] = None
    status: TaskStatus
    assignee_id: Optional[int] = None
    created_by_id: Optional[int] = None
    due_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentOut(ORMModel):
    id: int
    task_id: int
    author_id: Optional[int] = None
    body: str
    created_at: datetime


class EventOut(ORMModel):
    id: int
    project_id: int
    actor_id: Optional[int] = None
    event_type: str
    entity_type: str
    entity_id: Optional[int] = None
    payload: Optional[dict] = None
    created_at: datetime


class NotifyOut(ORMModel):
    id: int
    type: NotificationType
    title: str
    message: Optional[str] = None
    link: Optional[str] = None
    payload: Optional[dict] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    actor: Optional[UserBrief] = None
