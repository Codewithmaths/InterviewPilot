"""Face-analysis endpoint: receives a sampled frame, classifies, persists, broadcasts."""
from __future__ import annotations

import base64
import time
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.entities import FaceAnalysisEvent
from app.services.face import FaceAnalysisUnavailable, get_face_service
from app.websocket.events import WSEventType, build_message
from app.websocket.manager import manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["face-analysis"])

MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4 MB


def _decode_image(b64: str) -> np.ndarray:
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid base64 payload") from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image too large")
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not decode image")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


@router.post("/face-analysis")
async def analyze_frame(
    body: dict, db: Session = Depends(get_db)
) -> dict:
    image_b64 = (body.get("image_base64") or "").strip()
    interview_id = body.get("interview_id")
    if not image_b64:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "image_base64 is required")

    settings = get_settings()
    try:
        rgb = await run_in_threadpool(_decode_image, image_b64)
        service = get_face_service()
        result = await run_in_threadpool(service.analyze, rgb)
    except FaceAnalysisUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    now = datetime.now(timezone.utc)
    payload = {
        "face_detected": result["face_detected"],
        "category": result["category"],
        "confidence": result["confidence"],
        "timestamp": now.isoformat(),
        "features": result.get("features"),
    }

    if interview_id is not None:
        try:
            event = FaceAnalysisEvent(
                interview_id=int(interview_id),
                face_detected=result["face_detected"],
                category=result["category"],
                confidence=result["confidence"],
                timestamp=now,
            )
            db.add(event)
            db.commit()
            await manager.broadcast(
                int(interview_id),
                build_message(WSEventType.FACE_ANALYSIS_UPDATED, payload, int(interview_id)),
            )
        except Exception as exc:
            logger.error("Could not persist face analysis event: %s", exc)

    payload["analysis_interval"] = settings.FACE_ANALYSIS_INTERVAL
    payload["disclaimer"] = (
        "Facial-expression analysis is an AI-generated visual cue and should not be "
        "treated as a definitive assessment of personality, confidence, mental state, "
        "or hiring suitability."
    )
    return payload
