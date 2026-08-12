"""WebSocket endpoint: connection management + WebRTC signaling relay."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.entities import Interview
from app.websocket.events import WSEventType, build_message
from app.websocket.manager import manager

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/{interview_id}")
async def ws_endpoint(ws: WebSocket, interview_id: int) -> None:
    role = ws.query_params.get("role", "candidate")
    if role not in ("interviewer", "candidate"):
        await ws.close(code=4400)
        return

    db: Session = next(get_db())
    try:
        interview = db.get(Interview, interview_id)
        if interview is None:
            await ws.close(code=4404)
            return
    finally:
        db.close()

    cid = await manager.connect(interview_id, role, ws)
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.CANDIDATE_CONNECTED if role == "candidate" else WSEventType.INTERVIEWER_CONNECTED,
            {"role": role, "connection_id": cid},
            interview_id,
            role,
        ),
    )
    logger.info("%s connected to interview %s (%s)", role, interview_id, cid)

    try:
        while True:
            raw = await ws.receive_json()
            await _handle_message(ws, interview_id, role, raw)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS error for %s: %s", cid, exc)
    finally:
        await manager.disconnect(interview_id, role, cid)


async def _handle_message(ws: WebSocket, interview_id: int, role: str, raw: dict[str, Any]) -> None:
    event_type = raw.get("type")
    if event_type == "JOIN":
        await ws.send_json(
            build_message(
                WSEventType.JOIN,
                {"role": role, "interview_id": interview_id},
                interview_id,
                role,
            )
        )
        return

    if event_type == "SIGNAL":
        payload = raw.get("payload") or {}
        kind = payload.get("kind")
        if kind in ("offer", "answer", "ice"):
            await manager.send_to_peer(
                interview_id,
                role,
                build_message(
                    WSEventType.SIGNAL,
                    {"from_role": role, "kind": kind, "payload": payload},
                    interview_id,
                    role,
                ),
            )
            return
        await manager.error(ws, "Unsupported signaling kind", "BAD_SIGNAL")
        return

    # State-driven lifecycle events: advance the interview state machine and echo
    # the event to both consoles so the live UX stays in sync.
    state_events = {
        "ANSWER_STARTED": "WAITING_FOR_ANSWER",
        "ANSWER_STOPPED": None,
        "TRANSCRIPTION_STARTED": "TRANSCRIBING",
    }
    if event_type in state_events:
        from app.services.interview import InterviewService

        db: Session = next(get_db())
        try:
            target = state_events[event_type]
            if target:
                service = InterviewService(db)
                try:
                    service.transition(interview_id, target)
                except Exception as exc:
                    logger.info("State not advanced (%s -> %s): %s", interview_id, target, exc)
            await manager.broadcast(
                interview_id,
                build_message(
                    WSEventType(event_type),
                    {"role": role, "payload": raw.get("payload") or {}},
                    interview_id,
                    role,
                ),
            )
        finally:
            db.close()
        return

    await manager.error(ws, f"Unsupported event type: {event_type}", "BAD_EVENT")
