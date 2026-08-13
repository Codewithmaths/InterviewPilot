# Architecture

## Components

### Frontend

`frontend/src/` contains a Vite React TypeScript application:

- `pages/`: Home, interviewer console, candidate console, report.
- `components/`: video, question, transcript, evaluation, follow-up, history, status, controls, and report components.
- `hooks/`: media permissions, WebRTC, audio recording, and sampled face frames.
- `lib/api.ts`: REST client.
- `lib/ws.ts`: reconnecting typed WebSocket client.
- `store/useInterviewStore.ts`: Zustand interview state.
- `types/`: shared frontend contracts.

### Backend

`backend/app/` is split into:

- `api/`: REST and WebSocket endpoints.
- `core/`: settings, database, and logging.
- `models/`: SQLAlchemy entities and enums.
- `schemas/`: Pydantic API and LLM schemas.
- `services/`: interview orchestration, LLM, evaluation, report, transcription, and face analysis.
- `websocket/`: event definitions and connection manager.
- `ai/prompts/`: isolated prompt templates.

## Interview State Machine

```text
CREATED -> READY -> RUNNING
RUNNING -> WAITING_FOR_ANSWER -> TRANSCRIBING -> EVALUATING
EVALUATING -> FOLLOW_UP -> WAITING_FOR_ANSWER
EVALUATING -> NEXT_QUESTION -> RUNNING
Any active state -> COMPLETED
```

Transitions are validated in `backend/app/services/interview.py`. The answer endpoint accepts a transcript after the frontend has emitted the preceding recording/transcription events; direct `RUNNING -> EVALUATING` is also allowed for retry and API-client robustness.

## Answer Pipeline

1. Candidate sends `ANSWER_STARTED` over WebSocket.
2. Browser records microphone audio with `MediaRecorder`.
3. Candidate sends `ANSWER_STOPPED` and `TRANSCRIPTION_STARTED`.
4. Audio is uploaded to `/api/transcription`.
5. Faster-Whisper returns text; raw audio is deleted after transcription.
6. Candidate submits the transcript to `/api/interviews/{id}/answers`.
7. EvaluationService persists the answer and structured LLM evaluation.
8. Partial answers create up to three persisted follow-up questions.
9. `EVALUATION_COMPLETED` is broadcast and history is refreshed.

## WebRTC

The interviewer is the offerer. The candidate is the answerer.

- Both browsers connect to `/ws/{interview_id}?role=...`.
- The interviewer creates an SDP offer after the candidate connects and local media is available.
- The candidate sets the offer, creates an answer, and sends it back.
- ICE candidates are relayed by the backend.
- Local tracks are attached when the peer is created or when media permission completes.
- ICE candidates received before a remote description are queued.
- Local host candidates work for localhost/LAN development. Production deployments need TURN.

## Face Analysis

The candidate browser samples one downscaled JPEG at `FACE_ANALYSIS_INTERVAL`. The backend runs MediaPipe FaceMesh and derives explainable geometry features for a visual cue category. No full video stream is sent to the LLM and no raw frame is persisted.

## Persistence

The application uses Supabase (PostgreSQL) through SQLAlchemy with the `psycopg2` driver. The model uses standard foreign keys and JSON columns. Database tables are created automatically during FastAPI startup.

## Production Path

For production, add authentication/authorization, HTTPS, TURN, PostgreSQL migrations (Alembic), Redis-backed WebSocket/signaling state, background workers for Whisper/LLM jobs, object storage only if recordings are explicitly enabled, rate limiting, audit logging, and tenant isolation.
