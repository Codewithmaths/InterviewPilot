# API Reference

Base URL: `http://127.0.0.1:8000`

Interactive documentation is available at `/docs` and the OpenAPI schema at `/openapi.json`.

## Interviews

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/interviews` | Create candidate/interview and generate questions. |
| `GET` | `/api/interviews` | List recent interviews. |
| `GET` | `/api/interviews/{id}` | Retrieve interview summary. |
| `GET` | `/api/interviews/room/{room_code}` | Resolve a candidate room code. |
| `POST` | `/api/interviews/{id}/start` | Start interview and publish question one. |
| `POST` | `/api/interviews/{id}/end` | Complete interview and calculate duration. |
| `GET` | `/api/interviews/{id}/state` | Read current state and question index. |
| `POST` | `/api/interviews/{id}/state` | Apply a validated state transition. |

## Questions and History

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/interviews/{id}/questions` | Interviewer questions including expected answers. |
| `GET` | `/api/interviews/{id}/candidate/questions` | Candidate-safe questions without expected answers. |
| `POST` | `/api/interviews/{id}/question/next` | Move to the next main question. |
| `POST` | `/api/interviews/{id}/question/repeat` | Repeat current question. |
| `POST` | `/api/interviews/{id}/question/{number}` | Move to a specific main question. |
| `GET` | `/api/interviews/{id}/history` | Chronological main and follow-up history. |

## Answers and Follow-ups

`POST /api/interviews/{id}/answers` accepts:

```json
{
  "question_id": 1,
  "transcript": "Candidate transcript",
  "duration_seconds": 42
}
```

Use `followup_id` instead of `question_id` for a follow-up answer. The endpoint stores and evaluates the transcript atomically. The response includes classification, score, reason, missing concepts, and follow-up text.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/interviews/{id}/followups` | List persisted follow-up questions and answered status. |
| `POST` | `/api/interviews/{id}/followups/{followup_id}/select` | Select a follow-up for the candidate. |
| `POST` | `/api/interviews/{id}/followups/{followup_id}/answer` | Compatibility endpoint for follow-up answer evaluation. |

## AI and Media

| Method | Path | Body | Purpose |
|---|---|---|---|
| `POST` | `/api/transcription` | Multipart `audio` upload | Local Faster-Whisper transcription. |
| `POST` | `/api/face-analysis` | `{image_base64, interview_id?}` | Analyze one sampled frame and optionally persist/broadcast the event. |
| `GET` | `/api/interviews/{id}/report` | None | Generate final report and statistics. |
| `GET` | `/api/health` | None | Service and LLM mode health check. |

## WebSocket

Connect to:

```text
ws://127.0.0.1:8000/ws/{interview_id}?role=interviewer
ws://127.0.0.1:8000/ws/{interview_id}?role=candidate
```

Messages have this shape:

```json
{
  "type": "QUESTION_CHANGED",
  "interview_id": 1,
  "role": "interviewer",
  "payload": {"question_id": 1, "question_number": 1}
}
```

Application event types include `INTERVIEW_STARTED`, `QUESTION_CHANGED`, `ANSWER_STARTED`, `ANSWER_STOPPED`, `TRANSCRIPTION_STARTED`, `TRANSCRIPTION_UPDATED`, `TRANSCRIPTION_COMPLETED`, `EVALUATION_STARTED`, `EVALUATION_COMPLETED`, `FOLLOWUP_GENERATED`, `FOLLOWUP_SELECTED`, `FACE_ANALYSIS_UPDATED`, `INTERVIEW_ENDED`, `STATE_CHANGED`, `ERROR`, and connection events.

WebRTC signaling uses `SIGNAL` messages with `payload.kind` set to `offer`, `answer`, or `ice`. The backend relays signaling only to the opposite role and does not handle media itself.
