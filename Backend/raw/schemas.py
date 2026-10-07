from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from .models import NotificationType
 
class UserBrief(BaseModel):
    id: int
    full_name: str
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
    
class NotifyOut(BaseModel):
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
 
    model_config = ConfigDict(from_attributes=True)


class TokenData(BaseModel):
    id: Optional[int]= None