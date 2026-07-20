"""WebSocket progress channel: one broadcast group, JSON events."""
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event: dict):
        for ws in list(self.active):
            try:
                await ws.send_json(event)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()
