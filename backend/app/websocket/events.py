"""Typed WebSocket event definitions shared between backend and frontend."""
from __future__ import annotations

import enum
from typing import Any, Literal

from pydantic import BaseModel


class WSEventType(str, enum.Enum):
    # Lifecycle
    INTERVIEW_STARTED = "INTERVIEW_STARTED"
    QUESTION_CHANGED = "QUESTION_CHANGED"
    INTERVIEW_ENDED = "INTERVIEW_ENDED"
    STATE_CHANGED = "STATE_CHANGED"

    # Answer pipeline
    ANSWER_STARTED = "ANSWER_STARTED"
    ANSWER_STOPPED = "ANSWER_STOPPED"
    TRANSCRIPTION_STARTED = "TRANSCRIPTION_STARTED"
    TRANSCRIPTION_UPDATED = "TRANSCRIPTION_UPDATED"
    TRANSCRIPTION_COMPLETED = "TRANSCRIPTION_COMPLETED"
    EVALUATION_STARTED = "EVALUATION_STARTED"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
    FOLLOWUP_GENERATED = "FOLLOWUP_GENERATED"
    FOLLOWUP_SELECTED = "FOLLOWUP_SELECTED"

    # Face analysis
    FACE_ANALYSIS_UPDATED = "FACE_ANALYSIS_UPDATED"

    # Connection
    CONNECTION_OPEN = "CONNECTION_OPEN"
    CANDIDATE_CONNECTED = "CANDIDATE_CONNECTED"
    INTERVIEWER_CONNECTED = "INTERVIEWER_CONNECTED"
    PEER_DISCONNECTED = "PEER_DISCONNECTED"
    CONNECTION_CLOSED = "CONNECTION_CLOSED"

    # Webrtc signaling
    JOIN = "JOIN"
    SIGNAL = "SIGNAL"
    WEBRTC_OFFER = "WEBRTC_OFFER"
    WEBRTC_ANSWER = "WEBRTC_ANSWER"
    WEBRTC_ICE = "WEBRTC_ICE"

    # Generic
    ERROR = "ERROR"


class WSMessage(BaseModel):
    type: WSEventType
    interview_id: int | None = None
    role: Literal["interviewer", "candidate"] | None = None
    payload: dict[str, Any] = {}
    sent_at: str | None = None


def build_message(
    event_type: WSEventType,
    payload: dict[str, Any] | None = None,
    interview_id: int | None = None,
    role: Literal["interviewer", "candidate"] | None = None,
) -> dict[str, Any]:
    return WSMessage(
        type=event_type,
        payload=payload or {},
        interview_id=interview_id,
        role=role,
    ).model_dump(mode="json")
