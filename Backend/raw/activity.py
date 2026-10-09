from sqlalchemy.orm import Session

from . import models
from .ws_manager import manager


def _pending(db: Session, name: str) -> list:
    return db.info.setdefault(name, [])


def record_event(db: Session, project_id: int, actor_id: int, event_type: str, entity_type: str,
                 entity_id: int = None, payload: dict = None):
    event = models.ActivityEvent(project_id=project_id, actor_id=actor_id, event_type=event_type,
                                 entity_type=entity_type, entity_id=entity_id, payload=payload)
    db.add(event)
    _pending(db, "realtime_events").append(event)
    return event


def notify(db: Session, user_id: int, actor_id: int, type: models.NotificationType, title: str,
           message: str = None, link: str = None, payload: dict = None):
    if user_id is None or user_id == actor_id:
        return None
    notification = models.Notification(user_id=user_id, actor_id=actor_id, type=type, title=title,
                                       message=message, link=link, payload=payload)
    db.add(notification)
    _pending(db, "realtime_notifications").append(notification)
    return notification


def commit(db: Session) -> None:
    """Commit atomically, then publish only data that actually reached the database."""
    events = db.info.pop("realtime_events", [])
    notifications = db.info.pop("realtime_notifications", [])
    db.commit()
    for event in events:
        db.refresh(event)
        recipients = [row[0] for row in db.query(models.ProjectMember.user_id).filter(
            models.ProjectMember.project_id == event.project_id
        ).all()]
        manager.send_to_users(recipients, {"type": "project.event", "data": {
            "id": event.id, "project_id": event.project_id, "actor_id": event.actor_id,
            "event_type": event.event_type, "entity_type": event.entity_type,
            "entity_id": event.entity_id, "payload": event.payload, "created_at": event.created_at.isoformat(),
        }})
    for notification in notifications:
        db.refresh(notification)
        manager.send_to_users([notification.user_id], {"type": "notification.created", "data": {
            "id": notification.id, "type": notification.type.value, "title": notification.title,
            "message": notification.message, "link": notification.link, "payload": notification.payload,
            "is_read": notification.is_read, "created_at": notification.created_at.isoformat(),
        }})
