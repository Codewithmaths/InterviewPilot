# InterviewPilot

InterviewPilot is an AI-assisted live interview platform with separate interviewer and candidate consoles. It combines Groq question generation and answer evaluation, local Faster-Whisper transcription, MediaPipe facial cues, WebRTC media, WebSocket state synchronization, SQLite persistence, and a final report dashboard.

## Features

- Generate 20-30 structured questions with expected answers.
- Support Technical, HR, Behavioral, Python, Machine Learning, Data Science, SQL, Software Engineering, and Custom interviews.
- Optional job-description alignment.
- Candidate camera and microphone permission flow.
- Real WebRTC audio/video with WebSocket SDP/ICE signaling.
- Typed real-time events for interview state, transcription, evaluation, follow-ups, face analysis, and connection status.
- Local Faster-Whisper transcription without permanent raw audio storage.
- Groq structured answer evaluation: Correct, Incorrect, Partially Correct, or Not Confirmed.
- Targeted 2-3 follow-up questions for partially correct answers.
- MediaPipe FaceMesh visual cues sampled at `FACE_ANALYSIS_INTERVAL`.
- Persistent chronological question, answer, evaluation, follow-up, face-event, and interview-event history.
- Explainable report scoring with facial cues kept separate from knowledge evaluation.
- Responsive interviewer and candidate React consoles.

## Architecture

```text
React/Vite consoles
  | REST: CRUD, transcription, face frames, reports
  | WebSocket: state/events + WebRTC signaling
  v
FastAPI application
  | SQLAlchemy / SQLite
  | Groq LLM service
  | Faster-Whisper service
  | MediaPipe/OpenCV service
  v
Persistent interview history and report data
```

See `ARCHITECTURE.md`, `API.md`, and `DATABASE.md` for details.

## Requirements

- Python 3.11+; tested with Python 3.12.
- Node.js 20+; tested with Node 22.
- A Groq API key for real LLM generation and evaluation.
- A browser with camera/microphone support for the live consoles.

## Installation

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
cd frontend
npm install
```

Edit `.env` and set `GROQ_API_KEY`. The root `.env` is gitignored and must never be committed.

## Run Backend

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `http://127.0.0.1:8000/api/health`

Interactive API documentation: `http://127.0.0.1:8000/docs`

## Run Frontend

From `frontend/`:

```powershell
npm run dev
```

Open `http://127.0.0.1:5173`.

The Vite development proxy forwards `/api` and `/ws` to the backend.

## Local LLM Development Mode

If `GROQ_API_KEY` is empty, the backend uses a clearly marked `TEMPORARY DEVELOPMENT MOCK` for offline development. To force this mode:

```text
LLM_MOCK_MODE=true
```

This mode is not a replacement for production Groq output.

## Testing

Backend tests use an isolated SQLite database and never make real Groq calls:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

Frontend unit tests:

```powershell
cd frontend
npm test
```

Frontend production build:

```powershell
npm run build
```

## Usage

1. Open the root page as the interviewer.
2. Create an interview with a candidate, type, difficulty, and 20-30 questions.
3. Copy the generated candidate URL.
4. Start the interview and grant interviewer camera/microphone permission.
5. Open the candidate URL in a second browser tab or device.
6. Grant candidate camera/microphone permission.
7. Conduct the interview. The candidate records answers; Whisper transcribes them and Groq evaluates them.
8. Select targeted follow-ups when an answer is partially correct.
9. End the interview and open the report from the interviewer dashboard.

## Troubleshooting

- `GROQ_API_KEY` errors: verify the key is valid and the selected `GROQ_MODEL` is available.
- Camera/microphone unavailable: use HTTPS or localhost, grant browser permission, and verify no other application has exclusive device access.
- Whisper startup is slow: the configured model is downloaded and cached on first use. `WHISPER_MODEL=tiny` is faster for local smoke tests.
- WebRTC connects locally but not across networks: configure a TURN server; STUN alone is not sufficient for all NATs.
- Face analysis unavailable: verify `mediapipe`, `opencv-python-headless`, and their native dependencies are installed.
- Backend unavailable in the frontend: start Uvicorn on port 8000 before starting Vite.

## Privacy and Security

- API keys are backend-only environment variables.
- Raw audio/video is not persisted by the application; transcripts and derived metadata are stored.
- Camera, microphone, transcription, AI evaluation, and facial-cue use are disclosed in the candidate UI.
- Facial cues are not medical or psychological facts and are not combined with knowledge scoring.
- The MVP has no authentication or authorization layer. Do not expose it publicly without adding identity, access control, HTTPS, rate limiting, and room authorization.

## Known Limitations

- Browser-level two-party WebRTC media testing requires two permission-capable browser sessions and was not automated in this environment. The signaling path and frontend wiring are implemented and WebSocket-tested.
- SQLite is suitable for the MVP only. PostgreSQL, a migration tool, background workers, and a shared signaling store are future production work.
- Facial categories are geometry-based visual cues, not validated psychological measurements.
- Resume upload, authentication, persistent raw recordings, and multi-tenant access control are not included.

## Project Documents

- `ARCHITECTURE.md`: modules, state machine, WebRTC/WebSocket design, deployment notes.
- `API.md`: REST and WebSocket contracts.
- `DATABASE.md`: SQLAlchemy entities and relationships.
- `SETUP.md`: environment and operational setup.
- `TRACEABILITY.md`: requirements mapped to implementation and tests.
