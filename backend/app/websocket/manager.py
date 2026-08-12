"""WebSocket connection manager.

Routes typed events to the appropriate room/role and relays WebRTC signaling
between the interviewer and candidate for a given interview.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger
from app.websocket.events import WSEventType, build_message

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # interview_id -> {role -> {connection_id: WebSocket}}
        self._rooms: dict[int, dict[str, dict[str, WebSocket]]] = defaultdict(
            lambda: {"interviewer": {}, "candidate": {}}
        )
        self._counter = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    async def connect(self, interview_id: int, role: str, ws: WebSocket) -> str:
        await ws.accept()
        async with self._lock:
            self._counter += 1
            cid = f"{role}-{self._counter}"
            self._rooms[interview_id][role][cid] = ws
        await self._send(
            ws,
            build_message(WSEventType.CONNECTION_OPEN, {"connection_id": cid}, interview_id, role),
        )
        return cid

    async def disconnect(self, interview_id: int, role: str, cid: str) -> None:
        async with self._lock:
            room = self._rooms.get(interview_id)
            if room and cid in room[role]:
                del room[role][cid]
        logger.info("Disconnected %s (%s) from interview %s", role, cid, interview_id)
        await self.broadcast(
            interview_id,
            build_message(
                WSEventType.PEER_DISCONNECTED,
                {"role": role, "connection_id": cid},
                interview_id,
            ),
        )

    # ------------------------------------------------------------------
    async def broadcast(self, interview_id: int, message: dict[str, Any]) -> None:
        room = self._rooms.get(interview_id)
        if not room:
            return
        for role_sockets in room.values():
            for cid, ws in list(role_sockets.items()):
                await self._send(ws, message)

    async def send_to_role(
        self, interview_id: int, role: str, message: dict[str, Any]
    ) -> None:
        sockets = self._rooms.get(interview_id, {}).get(role, {})
        for cid, ws in list(sockets.items()):
            await self._send(ws, message)

    async def send_to_peer(
        self, interview_id: int, sender_role: str, message: dict[str, Any]
    ) -> None:
        """Send to the opposite role (used for WebRTC signaling)."""
        target_role = "candidate" if sender_role == "interviewer" else "interviewer"
        await self.send_to_role(interview_id, target_role, message)

    async def error(self, ws: WebSocket, message: str, code: str = "ERROR") -> None:
        await self._send(
            ws, build_message(WSEventType.ERROR, {"message": message, "code": code})
        )

    @staticmethod
    async def _send(ws: WebSocket, message: dict[str, Any]) -> None:
        try:
            await ws.send_json(message)
        except Exception as exc:  # socket closed during send
            logger.warning("WS send failed: %s", exc)


manager = ConnectionManager()
