"""Answer evaluation pipeline: persist answers, run LLM evaluation.

Services are synchronous and return rich results; the async API layer is
responsible for broadcasting WebSocket events.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.entities import (
    Answer,
    Evaluation,
    FollowUpQuestion,
    Interview,
    InterviewState,
    Question,
)
from app.schemas.llm import EvaluationResult
from app.services.llm import LLMService

logger = get_logger(__name__)


class EvaluationService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm or LLMService()

    # ------------------------------------------------------------------
    def evaluate_main_answer(
        self,
        interview_id: int,
        question_id: int,
        transcript: str,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        interview = self._get_interview(interview_id)
        question = self.db.get(Question, question_id)
        if question is None or question.interview_id != interview_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

        self._transition(interview, InterviewState.EVALUATING.value)

        answer = Answer(
            interview_id=interview_id,
            question_id=question.id,
            is_followup=False,
            transcript=transcript,
            duration_seconds=duration_seconds,
        )
        self.db.add(answer)
        self.db.flush()

        result = self.llm.evaluate_answer(
            question=question.question,
            topic=question.topic,
            difficulty=question.difficulty,
            expected_answer=question.expected_answer,
            candidate_answer=transcript,
        )
        self._persist_evaluation(answer, result)
        interview.total_questions_asked += 1

        payload = {
            "answer_id": answer.id,
            "question_id": question_id,
            "followup_id": None,
            "is_followup": False,
            "transcript": transcript,
            "classification": result.classification,
            "score": result.score,
            "reason": result.reason,
            "missing_concepts": result.missing_concepts,
            "metrics": [m.model_dump() for m in result.metrics],
            "follow_up_required": result.follow_up_required,
            "follow_up_questions": result.follow_up_questions,
            "followup_ids": [],
        }

        if result.follow_up_required:
            self._create_followups(interview, question, result)
            interview.status = InterviewState.FOLLOW_UP.value
            payload["followup_ids"] = [
                fu.id for fu in self._latest_followups(question)
            ]
        else:
            interview.status = InterviewState.NEXT_QUESTION.value
        self.db.commit()
        self.db.refresh(answer)
        return {"answer": answer, "evaluation": result, "payload": payload}

    # ------------------------------------------------------------------
    def evaluate_followup_answer(
        self,
        interview_id: int,
        followup_id: int,
        transcript: str,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        interview = self._get_interview(interview_id)
        followup = self.db.get(FollowUpQuestion, followup_id)
        if followup is None or followup.interview_id != interview_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up not found")

        self._transition(interview, InterviewState.EVALUATING.value)

        answer = Answer(
            interview_id=interview_id,
            followup_id=followup.id,
            is_followup=True,
            transcript=transcript,
            duration_seconds=duration_seconds,
        )
        self.db.add(answer)
        self.db.flush()

        parent = self.db.get(Question, followup.question_id)
        result = self.llm.evaluate_answer(
            question=followup.text,
            topic=parent.topic if parent else "Follow-up",
            difficulty=parent.difficulty if parent else "Medium",
            expected_answer=parent.expected_answer if parent else "",
            candidate_answer=transcript,
        )
        self._persist_evaluation(answer, result)
        interview.total_questions_asked += 1
        interview.follow_up_questions_count += 1
        # Stay in FOLLOW_UP while sibling follow-ups remain unanswered so the
        # interviewer can ask the next one; otherwise resume the main flow.
        if self._has_pending_followups(followup):
            interview.status = InterviewState.FOLLOW_UP.value
        else:
            interview.status = InterviewState.RUNNING.value
        self.db.commit()
        self.db.refresh(answer)

        payload = {
            "answer_id": answer.id,
            "question_id": None,
            "followup_id": followup_id,
            "is_followup": True,
            "transcript": transcript,
            "classification": result.classification,
            "score": result.score,
            "reason": result.reason,
            "missing_concepts": result.missing_concepts,
            "metrics": [m.model_dump() for m in result.metrics],
            "follow_up_required": False,
            "follow_up_questions": [],
            "followup_ids": [],
        }
        return {"answer": answer, "evaluation": result, "payload": payload}

    # ------------------------------------------------------------------
    def select_followup(self, interview_id: int, followup_id: int) -> FollowUpQuestion:
        interview = self._get_interview(interview_id)
        if interview.status != InterviewState.FOLLOW_UP.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No pending follow-ups in the current state",
            )
        followup = self.db.get(FollowUpQuestion, followup_id)
        if followup is None or followup.interview_id != interview_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up not found")
        already_answered = (
            self.db.query(Answer).filter(Answer.followup_id == followup.id).first()
        )
        if already_answered is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Follow-up already answered")
        interview.status = InterviewState.WAITING_FOR_ANSWER.value
        self.db.commit()
        self.db.refresh(followup)
        return followup

    # ------------------------------------------------------------------
    def _has_pending_followups(self, followup: FollowUpQuestion) -> bool:
        """True when sibling follow-ups of the same question remain unanswered."""
        pending = (
            self.db.query(FollowUpQuestion)
            .outerjoin(Answer, Answer.followup_id == FollowUpQuestion.id)
            .filter(FollowUpQuestion.question_id == followup.question_id)
            .filter(Answer.id.is_(None))
            .count()
        )
        return pending > 0

    # ------------------------------------------------------------------
    def _create_followups(
        self, interview: Interview, question: Question, result: EvaluationResult
    ) -> None:
        questions = result.follow_up_questions or self.llm.generate_followups(
            question=question.question,
            topic=question.topic,
            candidate_answer="",
            reason=result.reason,
            missing_concepts=result.missing_concepts,
        )
        existing_count = (
            self.db.query(FollowUpQuestion)
            .filter(FollowUpQuestion.question_id == question.id)
            .count()
        )
        for i, text in enumerate(questions[:3], start=existing_count + 1):
            self.db.add(
                FollowUpQuestion(
                    interview_id=interview.id,
                    question_id=question.id,
                    followup_number=i,
                    text=text,
                )
            )
        self.db.flush()

    @staticmethod
    def _latest_followups(question: Question) -> list[FollowUpQuestion]:
        from sqlalchemy.orm import object_session

        session = object_session(question)
        if session is None:
            return []
        rows = (
            session.query(FollowUpQuestion)
            .filter(FollowUpQuestion.question_id == question.id)
            .order_by(FollowUpQuestion.followup_number)
            .all()
        )
        return rows[-3:]

    # ------------------------------------------------------------------
    def _persist_evaluation(self, answer: Answer, result: EvaluationResult) -> Evaluation:
        evaluation = Evaluation(
            answer_id=answer.id,
            classification=result.classification,
            score=result.score,
            reason=result.reason,
            missing_concepts=result.missing_concepts,
            metric_scores=[m.model_dump() for m in result.metrics],
            follow_up_required=result.follow_up_required,
            follow_up_questions=result.follow_up_questions,
        )
        self.db.add(evaluation)
        self.db.flush()
        return evaluation

    def _get_interview(self, interview_id: int) -> Interview:
        interview = self.db.get(Interview, interview_id)
        if interview is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")
        return interview

    def _transition(self, interview: Interview, target: str) -> None:
        from app.services.interview import StateTransitionError, TRANSITIONS

        allowed = TRANSITIONS.get(interview.status, set())
        if target not in allowed:
            raise StateTransitionError(
                f"Invalid state transition {interview.status} -> {target}"
            )
        interview.status = target
