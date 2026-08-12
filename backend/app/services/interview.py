"""Interview orchestration: creation, lifecycle, state machine, question flow."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.entities import (
    Candidate,
    FaceAnalysisEvent,
    FollowUpQuestion,
    Interview,
    InterviewEvent,
    InterviewState,
    Question,
)
from app.schemas.interview import InterviewCreate
from app.services.llm import LLMService
from app.websocket.events import WSEventType, build_message
from app.websocket.manager import manager

logger = get_logger(__name__)


class StateTransitionError(Exception):
    pass


# Allowed state transitions (from_state -> set of allowed to_states)
TRANSITIONS: dict[str, set[str]] = {
    InterviewState.CREATED.value: {
        InterviewState.READY.value,
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.READY.value: {
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.RUNNING.value: {
        InterviewState.WAITING_FOR_ANSWER.value,
        InterviewState.TRANSCRIBING.value,
        InterviewState.EVALUATING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.WAITING_FOR_ANSWER.value: {
        InterviewState.TRANSCRIBING.value,
        InterviewState.EVALUATING.value,
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.TRANSCRIBING.value: {
        InterviewState.EVALUATING.value,
        InterviewState.WAITING_FOR_ANSWER.value,
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.EVALUATING.value: {
        InterviewState.FOLLOW_UP.value,
        InterviewState.NEXT_QUESTION.value,
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.FOLLOW_UP.value: {
        InterviewState.WAITING_FOR_ANSWER.value,
        InterviewState.EVALUATING.value,
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.NEXT_QUESTION.value: {
        InterviewState.RUNNING.value,
        InterviewState.COMPLETED.value,
    },
    InterviewState.COMPLETED.value: set(),
}


def _ensure_state(interview: Interview, allowed: set[str]) -> None:
    if interview.status not in allowed:
        raise StateTransitionError(
            f"Invalid state transition: {interview.status} not in {sorted(allowed)}"
        )


def _generate_room_code() -> str:
    return secrets.token_urlsafe(12)


class InterviewService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm or LLMService()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    def create_interview(self, data: InterviewCreate, base_url: str | None = None) -> Interview:
        candidate = (
            self.db.query(Candidate)
            .filter(Candidate.email == data.candidate_email.lower())
            .first()
        )
        if candidate is None:
            candidate = Candidate(name=data.candidate_name, email=data.candidate_email.lower())
            self.db.add(candidate)
            self.db.flush()

        interview = Interview(
            candidate_id=candidate.id,
            interview_type=data.interview_type,
            difficulty=data.difficulty,
            num_questions=data.num_questions,
            job_description=data.job_description,
            room_code=_generate_room_code(),
        )
        self.db.add(interview)
        self.db.flush()

        batch = self.llm.generate_questions(
            interview_type=data.interview_type,
            difficulty=data.difficulty,
            num_questions=data.num_questions,
            candidate_name=data.candidate_name,
            job_description=data.job_description,
        )
        for draft in batch.questions:
            self.db.add(
                Question(
                    interview_id=interview.id,
                    question_number=draft.question_number,
                    question=draft.question,
                    expected_answer=draft.expected_answer,
                    topic=draft.topic,
                    difficulty=draft.difficulty,
                )
            )
        interview.main_questions_count = len(batch.questions)
        # Generated questions are not counted as asked until the candidate answers.
        interview.total_questions_asked = 0

        if base_url:
            interview.join_url = (
                f"{base_url.rstrip('/')}/candidate/{interview.id}/{interview.room_code}"
            )
        self.db.commit()
        self.db.refresh(interview)
        logger.info("Created interview %s for %s", interview.id, candidate.email)
        return interview

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, interview_id: int) -> Interview:
        interview = self._get(interview_id)
        _ensure_state(interview, {InterviewState.CREATED.value, InterviewState.READY.value})
        interview.status = InterviewState.RUNNING.value
        interview.started_at = interview.started_at or datetime.now(timezone.utc)
        first_question = (
            self.db.query(Question)
            .filter(Question.interview_id == interview_id)
            .order_by(Question.question_number)
            .first()
        )
        if first_question is not None:
            interview.current_question_id = first_question.id
            interview.current_question_index = first_question.question_number
            self.db.add(
                InterviewEvent(
                    interview_id=interview.id,
                    event_type=WSEventType.QUESTION_CHANGED.value,
                    payload={
                        "question_number": first_question.question_number,
                        "question_id": first_question.id,
                    },
                )
            )
        self.db.add(InterviewEvent(interview_id=interview.id, event_type=WSEventType.INTERVIEW_STARTED.value))
        self.db.commit()
        self.db.refresh(interview)
        return interview

    def end(self, interview_id: int) -> Interview:
        interview = self._get(interview_id)
        if interview.status == InterviewState.COMPLETED.value:
            return interview
        interview.status = InterviewState.COMPLETED.value
        interview.ended_at = datetime.now(timezone.utc)
        if interview.started_at and interview.ended_at:
            start = interview.started_at
            end = interview.ended_at
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            interview.duration_seconds = max(0, int((end - start).total_seconds()))
        self.db.add(InterviewEvent(interview_id=interview.id, event_type=WSEventType.INTERVIEW_ENDED.value))
        self.db.commit()
        self.db.refresh(interview)
        return interview

    def transition_to(self, interview: Interview, target: str) -> Interview:
        allowed = TRANSITIONS.get(interview.status, set())
        if target not in allowed:
            raise StateTransitionError(
                f"Invalid state transition {interview.status} -> {target}"
            )
        prev = interview.status
        interview.status = target
        self.db.add(
            InterviewEvent(
                interview_id=interview.id,
                event_type=WSEventType.STATE_CHANGED.value,
                payload={"from": prev, "to": target},
            )
        )
        self.db.commit()
        self.db.refresh(interview)
        return interview

    def transition(self, interview_id: int, target: str) -> Interview:
        """Public helper to advance the interview state machine."""
        interview = self._get(interview_id)
        return self.transition_to(interview, target)

    # ------------------------------------------------------------------
    # Question flow
    # ------------------------------------------------------------------
    def move_to_question(self, interview_id: int, question_number: int) -> Question:
        interview = self._get(interview_id)
        _ensure_state(
            interview,
            {
                InterviewState.RUNNING.value,
                InterviewState.NEXT_QUESTION.value,
                InterviewState.FOLLOW_UP.value,
                InterviewState.WAITING_FOR_ANSWER.value,
            },
        )
        question = (
            self.db.query(Question)
            .filter(Question.interview_id == interview_id)
            .filter(Question.question_number == question_number)
            .first()
        )
        if question is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
        interview.current_question_id = question.id
        interview.current_question_index = question_number
        interview.status = InterviewState.RUNNING.value
        self.db.add(
            InterviewEvent(
                interview_id=interview_id,
                event_type=WSEventType.QUESTION_CHANGED.value,
                payload={"question_number": question_number, "question_id": question.id},
            )
        )
        self.db.commit()
        self.db.refresh(question)
        return question

    def next_question(self, interview_id: int) -> Question | None:
        interview = self._get(interview_id)
        _ensure_state(interview, {InterviewState.RUNNING.value, InterviewState.NEXT_QUESTION.value})
        next_number = (interview.current_question_index or 0) + 1
        question = (
            self.db.query(Question)
            .filter(Question.interview_id == interview_id)
            .filter(Question.question_number == next_number)
            .first()
        )
        if question is None:
            return None
        return self.move_to_question(interview_id, next_number)

    def repeat_question(self, interview_id: int) -> Question | None:
        interview = self._get(interview_id)
        _ensure_state(interview, {InterviewState.RUNNING.value})
        if not interview.current_question_index:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No current question to repeat")
        return self.move_to_question(interview_id, interview.current_question_index)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def _get(self, interview_id: int) -> Interview:
        interview = self.db.get(Interview, interview_id)
        if interview is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")
        return interview

    def get(self, interview_id: int) -> Interview:
        return self._get(interview_id)

    def get_by_room(self, room_code: str) -> Interview:
        interview = self.db.query(Interview).filter(Interview.room_code == room_code).first()
        if interview is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")
        return interview

    def list_interviews(self) -> list[Interview]:
        return (
            self.db.query(Interview).order_by(Interview.created_at.desc()).limit(200).all()
        )

    def get_questions(self, interview_id: int) -> list[Question]:
        self._get(interview_id)
        return (
            self.db.query(Question)
            .filter(Question.interview_id == interview_id)
            .order_by(Question.question_number)
            .all()
        )

    def get_history(self, interview_id: int) -> list[dict]:
        """Chronological history: main questions and follow-ups with all answers/evaluations."""
        interview = self._get(interview_id)
        questions = self.get_questions(interview_id)
        history: list[dict] = []
        for question in questions:
            followups = (
                self.db.query(FollowUpQuestion)
                .filter(FollowUpQuestion.question_id == question.id)
                .order_by(FollowUpQuestion.followup_number)
                .all()
            )
            from app.models.entities import Answer

            main_answers = (
                self.db.query(Answer)
                .filter(Answer.question_id == question.id, Answer.is_followup.is_(False))
                .order_by(Answer.created_at.asc())
                .all()
            )
            history.append(
                {
                    "question_number": question.question_number,
                    "question": question.question,
                    "expected_answer": question.expected_answer,
                    "topic": question.topic,
                    "difficulty": question.difficulty,
                    "is_followup": False,
                    "followup_text": None,
                    "answers": main_answers,
                }
            )
            for fu in followups:
                fu_answers = (
                    self.db.query(Answer)
                    .filter(Answer.followup_id == fu.id)
                    .order_by(Answer.created_at.asc())
                    .all()
                )
                history.append(
                    {
                        "question_number": question.question_number,
                        "question": question.question,
                        "expected_answer": question.expected_answer,
                        "topic": question.topic,
                        "difficulty": question.difficulty,
                        "is_followup": True,
                        "followup_text": fu.text,
                        "answers": fu_answers,
                    }
                )
        return history

    def list_face_events(self, interview_id: int) -> list[FaceAnalysisEvent]:
        return (
            self.db.query(FaceAnalysisEvent)
            .filter(FaceAnalysisEvent.interview_id == interview_id)
            .order_by(FaceAnalysisEvent.timestamp.asc())
            .all()
        )
