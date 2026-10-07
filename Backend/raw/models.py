from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


# --- ENUMS ---

class UserRole(str, Enum):
    """Global (app-wide) role."""
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class ProjectRole(str, Enum):
    """Per-project role. A user can be a LEAD in one project and a MEMBER in another."""
    PROJECT_LEAD = "PROJECT_LEAD"
    MEMBER = "MEMBER"


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"


class NotificationType(str, Enum):
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
    TASK_COMMENTED = "TASK_COMMENTED"
    ADDED_TO_PROJECT = "ADDED_TO_PROJECT"
    REMOVED_FROM_PROJECT = "REMOVED_FROM_PROJECT"
    ROLE_CHANGED = "ROLE_CHANGED"
    SYSTEM = "SYSTEM"


# --- AUTH ---

class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True, default=None)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.MEMBER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", foreign_keys="Notification.user_id",
                                 cascade="all, delete-orphan")


class RefreshToken(Base):
    """
    One row per login session/device. Store only a HASH of the token.
    Rotate on every refresh: revoke the old row, create a new one, and link them
    via replaced_by_id. If a revoked token is ever reused, revoke the whole family.
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    family_id = Column(String, nullable=False, index=True)  # uuid shared by a rotation chain
    replaced_by_id = Column(Integer, ForeignKey("refresh_tokens.id"), nullable=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("Users", back_populates="refresh_tokens")


# --- PROJECTS & RBAC ---

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    """Join table that carries the per-project role (this is what RBAC checks hit)."""
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_user"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SAEnum(ProjectRole), nullable=False, default=ProjectRole.MEMBER)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="members")
    user = relationship("Users", back_populates="memberships")


# --- TASKS ---

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TaskStatus), nullable=False, default=TaskStatus.TODO, index=True)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="tasks")
    assignee = relationship("Users", foreign_keys=[assignee_id])
    created_by = relationship("Users", foreign_keys=[created_by_id])
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", back_populates="comments")
    author = relationship("Users")


# --- REAL-TIME EVENTS & NOTIFICATIONS ---

class ActivityEvent(Base):
    """
    Append-only log of things that happened in a project (task created, status
    changed, member added...). Broadcast each row over your WebSocket / Supabase
    channel after commit. Clients that reconnect can replay missed events with
    `WHERE project_id = ? AND id > last_seen_id`.
    """
    __tablename__ = "activity_events"
    __table_args__ = (Index("ix_activity_project_id_id", "project_id", "id"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String, nullable=False)    # e.g. "task.status_changed"
    entity_type = Column(String, nullable=False)   # "task", "project", "member"
    entity_id = Column(Integer, nullable=True)
    payload = Column(JSON, nullable=True)          # before/after values, titles, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    actor = relationship("Users")


class Notification(Base):
    """Per-user inbox. Powers the notification bell, unread badge and toast feed."""
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "is_read"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # recipient
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # who caused it
    type = Column(SAEnum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String, nullable=True)          
    payload = Column(JSON, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("Users", back_populates="notifications", foreign_keys=[user_id])
    actor = relationship("Users", foreign_keys=[actor_id])


# --- OPTIONAL: CENTRALIZED ERROR HANDLING ---

class ErrorLog(Base):
    """
    E xception handler for unexpected (5xx) errors,
    so the frontend toast can show a friendly message + request_id to quote in
    bug reports. Expected errors (401/403/404/422) don't need a table.
    """
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True)
    request_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    method = Column(String, nullable=False)
    path = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    error_type = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())