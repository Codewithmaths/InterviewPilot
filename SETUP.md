# Setup and Operations

## Environment

Copy `.env.example` to `.env` in the project root. Required values:

```text
GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_URL=http://127.0.0.1:5173
FACE_ANALYSIS_INTERVAL=1.0
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

`DATABASE_URL` is required and must be a Supabase (PostgreSQL) connection string from the dashboard (Project Settings -> Database -> Connection string -> Session pooler).

Never place `GROQ_API_KEY` in frontend environment variables or source code.

## Backend

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The first transcription request may download the Whisper model. Database tables are initialized automatically on startup.

## Frontend

```powershell
npm install
npm run dev
```

Vite serves on port 5173 and proxies `/api` and `/ws` to port 8000.

## Verification

```powershell
..\.venv\Scripts\python.exe -m pytest
npm test
npm run build
```

## Deployment Notes

- Use HTTPS so browsers permit camera/microphone access outside localhost.
- Set `FRONTEND_URL` to the public frontend origin.
- Configure a TURN server and pass its ICE credentials to `frontend/src/hooks/useWebRTC.ts`.
- Add a migration tool (e.g. Alembic) and a shared WebSocket/signaling store such as Redis when running multiple API workers.
- Add authentication and authorization before sharing interview links publicly.
- Add a shared WebSocket/signaling backend such as Redis when running multiple API workers.
