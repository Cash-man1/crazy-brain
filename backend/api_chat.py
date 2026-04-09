"""
Live chat (WebSocket) + active users count.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, Dict, Any
import asyncio
import json
import time

router = APIRouter(prefix="/chat", tags=["Live Chat"])


class ConnectionManager:
    def __init__(self):
        self._active: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._active.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self._active.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        data = json.dumps(message, ensure_ascii=False)
        async with self._lock:
            targets = list(self._active)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                try:
                    await self.disconnect(ws)
                except Exception:
                    pass

    async def active_count(self) -> int:
        async with self._lock:
            return len(self._active)


manager = ConnectionManager()


@router.get("/active")
async def get_active():
    return {"active_users": await manager.active_count()}


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await manager.broadcast({"type": "presence", "active_users": await manager.active_count(), "ts": time.time()})
        while True:
            text = await websocket.receive_text()
            msg = (text or "").strip()
            if not msg:
                continue
            await manager.broadcast({"type": "message", "text": msg[:500], "ts": time.time()})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        await manager.broadcast({"type": "presence", "active_users": await manager.active_count(), "ts": time.time()})
    except Exception:
        await manager.disconnect(websocket)
        await manager.broadcast({"type": "presence", "active_users": await manager.active_count(), "ts": time.time()})

