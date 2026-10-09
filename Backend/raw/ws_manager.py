import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Keeps sockets grouped by user so notifications never leak between users."""

    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[user_id].add(websocket)
        self._loop = asyncio.get_running_loop()

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        self.connections[user_id].discard(websocket)
        if not self.connections[user_id]:
            self.connections.pop(user_id, None)

    async def _send_to_users(self, user_ids: list[int], message: dict[str, Any]) -> None:
        stale: list[tuple[int, WebSocket]] = []
        for user_id in set(user_ids):
            for socket in list(self.connections.get(user_id, ())):
                try:
                    await socket.send_json(message)
                except Exception:
                    stale.append((user_id, socket))
        for user_id, socket in stale:
            self.disconnect(user_id, socket)

    def send_to_users(self, user_ids: list[int], message: dict[str, Any]) -> None:
        """Safe to call from FastAPI's synchronous route worker threads."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._send_to_users(user_ids, message), self._loop)


manager = ConnectionManager()
