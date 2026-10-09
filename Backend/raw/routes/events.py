from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from .. import models,schemas,oauth,rbac
from ..database import get_db
from typing import List


router = APIRouter(tags=["Events"])


# Catch-up endpoint: after a WebSocket drops and reconnects, the client asks
# "give me everything after the last event id I saw".
@router.get("/projects/{project_id}/events",response_model=List[schemas.EventOut])
def get_events(
    project_id:int,
    after_id:int = 0,
    limit:int = Query(50,ge=1,le=200),
    db:Session = Depends(get_db),
    current_user:models.Users = Depends(oauth.get_current_user)):
    rbac.get_project_or_404(db,project_id)
    rbac.require_member(db,project_id,current_user)

    return db.query(models.ActivityEvent).filter(
        models.ActivityEvent.project_id == project_id,
        models.ActivityEvent.id > after_id
    ).order_by(models.ActivityEvent.id.asc()).limit(limit).all()
