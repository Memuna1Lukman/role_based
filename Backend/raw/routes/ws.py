from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from starlette.concurrency import run_in_threadpool
from typing import Optional
from .. import models, oauth
from ..config import settings
from ..database import get_db
from ..ws_manager import manager


router = APIRouter(tags=["Realtime"])

# Browsers send an Origin header on WebSocket connections. Since we log in with a cookie,
# we must only accept connections from OUR frontend, otherwise any website the user visits
# could open a socket as them. Put your real frontend URL(s) here.
ALLOWED_ORIGINS = {origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()}


def authenticate_user(token: Optional[str]) -> Optional[int]:
    """Returns the user id for a valid access token, or None."""
    if not token:
        return None
    credentials_exception = HTTPException(status_code=401, detail="Invalid token")
    try:
        token_data = oauth.verify_token(token, credentials_exception)
    except HTTPException:
        return None

    # open a short-lived db session just for this check (we don't hold one open for the whole socket)
    db_gen = get_db()
    db = next(db_gen)
    try:
        user = db.query(models.Users).filter(models.Users.id == token_data.id).first()
        if not user or not user.is_active:
            return None
        return user.id
    finally:
        db_gen.close()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    # the browser sends the access_token cookie automatically with the connection request
    token = websocket.cookies.get("access_token")
    user_id = await run_in_threadpool(authenticate_user, token)
    if user_id is None:
        await websocket.close(code=1008)  # 1008 = policy violation (not allowed)
        return

    await manager.connect(user_id, websocket)
    try:
        # We only RECEIVE here to detect when the browser disconnects.
        # The client can send "ping" now and then to keep the connection alive.
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, websocket)
