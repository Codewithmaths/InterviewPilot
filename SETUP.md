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

Transcription uses the hosted Groq Whisper API by default (`STT_PROVIDER=groq`). To run faster-whisper locally instead, set `STT_PROVIDER=local` (the first request then downloads the Whisper model). Database tables are initialized automatically on startup.

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
- Add authentication and authorization before sharing interview links publicly.
- Add a shared WebSocket/signaling backend such as Redis when running multiple API workers.

## Free deployment (Render)

`render.yaml` deploys everything as one free web service (FastAPI serves the built
Vite frontend on the same origin, so REST, `/ws`, and the SPA share one host).

1. Push this repo to GitHub.
2. In Render: **New -> Blueprint** -> select the repo -> **Apply**. Pick the free plan.
3. In the service's **Environment** tab set the secrets (never commit them):
   - `DATABASE_URL` — your Supabase session-pooler connection string
   - `GROQ_API_KEY`
   - `FRONTEND_URL` — your public origin
   - `CORS_ORIGINS` — the same public origin
4. For camera/mic on a custom name, add `interviewpilot.duckdns.org` in
   **Settings -> Custom Domains**, then point a DuckDNS `CNAME` record at your
   `<service>.onrender.com` URL. Render provisions the TLS certificate.

The Groq LLM + Whisper API, Supabase, and the Google/Cloudflare STUN + Open Relay
TURN servers (in `frontend/src/hooks/useWebRTC.ts`) are all free tiers.
