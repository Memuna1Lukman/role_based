from sqlalchemy.orm import Session
from . import models


def record_event(
    db: Session,
    project_id: int,
    actor_id: int,
    event_type: str,
    entity_type: str,
    entity_id: int = None,
    payload: dict = None,
):
    """
    Adds an ActivityEvent to the session. It does NOT commit, so the event is saved
    in the same transaction as the change that caused it.
    Later: after db.commit() in the endpoint, broadcast this event over WebSocket / Supabase.
    """
    event = models.ActivityEvent(
        project_id=project_id,
        actor_id=actor_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    db.add(event)
    return event


def notify(
    db: Session,
    user_id: int,
    actor_id: int,
    type: models.NotificationType,
    title: str,
    message: str = None,
    link: str = None,
    payload: dict = None,
):
    """Adds a Notification for user_id. Skips if there's no recipient or the recipient is the actor."""
    if user_id is None or user_id == actor_id:
        return None
    notification = models.Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type,
        title=title,
        message=message,
        link=link,
        payload=payload,
    )
    db.add(notification)
    return notification