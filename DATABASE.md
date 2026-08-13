# Database Design

The application uses Supabase (PostgreSQL) with SQLAlchemy 2.x and the `psycopg2` driver. `Base.metadata.create_all()` runs on application startup and creates the tables, enum types, and indexes automatically — no manual SQL is required. The connection is configured via `DATABASE_URL` in `.env` (see `SETUP.md`).

## Entities

### Candidate

Stores name, email, and creation time. One candidate can have multiple interviews.

### Interview

Stores interview type, difficulty, main question count, room code, status, timestamps, current question, follow-up counters, and duration.

### Question

Stores the generated question number, question text, expected answer, topic, difficulty, and interview relationship.

### Answer

Stores a transcript for either a main question or a follow-up. Exactly one of `question_id` and `followup_id` is expected for normal records.

### Evaluation

Stores the answer classification, score, reason, missing concepts, follow-up-required flag, and structured follow-up text.

### FollowUpQuestion

Stores up to three targeted follow-ups linked to the original main question and interview.

### FaceAnalysisEvent

Stores only derived face-analysis metadata: detected flag, category, confidence, and timestamp. Raw frames are not stored.

### InterviewEvent

Stores chronological lifecycle and synchronization events with JSON payloads.

## Relationships

```text
Candidate 1 ─── * Interview
Interview 1 ─── * Question
Question 1 ─── * Answer
Question 1 ─── * FollowUpQuestion
FollowUpQuestion 1 ─── * Answer
Answer 1 ─── 0..1 Evaluation
Interview 1 ─── * FaceAnalysisEvent
Interview 1 ─── * InterviewEvent
```

## Scoring

The report uses the configurable MVP methodology:

```text
Correct = 1.0
Partially Correct = 0.5
Incorrect = 0.0
Not Confirmed = excluded
```

The score is an AI-assisted estimate and is not an objective hiring score.
