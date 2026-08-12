"""Computer vision service for candidate facial analysis.

Uses MediaPipe FaceMesh to detect the face and extract landmark geometry, then
computes an explainable heuristic for visual engagement categories.

IMPORTANT: These categories are AI-generated visual cues and must NOT be treated
as a definitive assessment of personality, confidence, mental state, or hiring
suitability. They are displayed in the UI with a disclaimer.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

FACIAL_DISCLAIMER = (
    "Facial-expression analysis is an AI-generated visual cue and should not be "
    "treated as a definitive assessment of personality, confidence, mental state, "
    "or hiring suitability."
)


class FaceAnalysisUnavailable(Exception):
    """Raised when the computer-vision backend cannot be initialised."""


def _mar(lms: np.ndarray) -> float:
    """Mouth aspect ratio: openness of the mouth (smile proxy)."""
    a = np.linalg.norm(lms[13] - lms[14])  # outer lip vertical
    b = np.linalg.norm(lms[78] - lms[308])  # mouth corner width
    if b < 1e-6:
        return 0.0
    return float(np.clip(a / b, 0.0, 1.2))


def _ear(lms: np.ndarray) -> float:
    """Eye aspect ratio: average openness of both eyes (blink proxy)."""
    left = np.linalg.norm(lms[159] - lms[145]) / max(np.linalg.norm(lms[33] - lms[133]), 1e-6)
    right = np.linalg.norm(lms[386] - lms[374]) / max(np.linalg.norm(lms[362] - lms[263]), 1e-6)
    return float((left + right) / 2.0)


def _pitch(lms: np.ndarray) -> float:
    """Approximate head pitch in degrees using landmark z (nose vs forehead).

    Positive value -> candidate looks downward. Negative -> looking up.
    """
    nose = lms[4]
    forehead = lms[10]
    chin = lms[152]
    depth = (nose[2] - forehead[2]) * 1000.0
    vertical = (chin[1] - forehead[1]) + 1e-6
    return float(np.degrees(np.arctan(depth / vertical)))


class FaceAnalysisService:
    """Analyzes a single RGB frame and classifies visual engagement."""

    def __init__(self, window_size: int = 8) -> None:
        self._face_mesh = None
        self._lock = threading.Lock()
        self._last_landmarks: np.ndarray | None = None
        self._window: deque[str] = deque(maxlen=window_size)
        self._jitter: deque[float] = deque(maxlen=window_size)

    # ------------------------------------------------------------------
    def _load_face_mesh(self):
        if self._face_mesh is not None:
            return self._face_mesh
        with self._lock:
            if self._face_mesh is not None:
                return self._face_mesh
            try:
                import mediapipe as mp

                self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            except Exception as exc:
                logger.error("FaceMesh initialisation failed: %s", exc)
                raise FaceAnalysisUnavailable(
                    "Facial analysis backend could not be initialised. "
                    "Install MediaPipe/OpenCV and their native dependencies."
                ) from exc
        return self._face_mesh

    # ------------------------------------------------------------------
    def analyze(self, image_rgb: np.ndarray) -> dict[str, Any]:
        """Analyze one RGB frame. Returns face_detected / category / confidence."""
        face_mesh = self._load_face_mesh()

        rgb = cv2.resize(image_rgb, (480, 480), interpolation=cv2.INTER_AREA)
        results = face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            self._last_landmarks = None
            self._window.append("Face Not Detected")
            self._jitter.append(0.0)
            return {
                "face_detected": False,
                "category": "Face Not Detected",
                "confidence": 1.0,
                "features": {},
            }

        lms = np.array(
            [(p.x, p.y, p.z) for p in results.multi_face_landmarks[0].landmark],
            dtype=np.float32,
        )

        smile = _mar(lms)
        ear = _ear(lms)
        pitch = _pitch(lms)

        movement = 0.0
        if self._last_landmarks is not None:
            face_scale = np.linalg.norm(lms[234] - lms[454]) + 1e-6
            movement = float(np.linalg.norm(lms[:10] - self._last_landmarks[:10]) / face_scale)
        self._last_landmarks = lms
        self._jitter.append(movement)

        category = self._classify(smile=smile, ear=ear, pitch=pitch, movement=movement)
        self._window.append(category)

        majority = max(set(self._window), key=self._window.count) if self._window else category
        confidence = self._window.count(majority) / max(len(self._window), 1)

        features = {
            "smile": round(smile, 3),
            "eye_openness": round(ear, 3),
            "head_pitch_deg": round(pitch, 1),
            "movement": round(movement, 3),
        }
        return {
            "face_detected": True,
            "category": majority,
            "confidence": round(confidence, 2),
            "features": features,
        }

    @staticmethod
    def _classify(smile: float, ear: float, pitch: float, movement: float) -> str:
        jitter = movement > 0.10

        if smile > 0.55 and movement > 0.05:
            return "Energetic"
        if smile > 0.35 and not jitter and -15.0 <= pitch <= 15.0:
            return "Confident"
        if movement > 0.14 and smile < 0.3:
            return "Nervous"
        if smile < 0.25 and pitch > 12.0:
            return "Low confident"
        if smile < 0.2 and movement < 0.02:
            return "Low confident"
        return "Confident"


_face_instance: FaceAnalysisService | None = None
_face_lock = threading.Lock()


def get_face_service() -> FaceAnalysisService:
    global _face_instance
    if _face_instance is None:
        with _face_lock:
            if _face_instance is None:
                _face_instance = FaceAnalysisService()
    return _face_instance
