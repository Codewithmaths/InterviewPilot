"""Final interview report generation: explainable scoring + LLM narrative."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.entities import (
    Answer,
    Evaluation,
    FaceAnalysisEvent,
    Interview,
    Question,
)
from app.schemas.interview import InterviewReport, QuestionReportItem
from app.services.llm import LLMService

logger = get_logger(__name__)

SCORING_METHODOLOGY = (
    "Answer-performance score = (Correct * 1.0 + Partially Correct * 0.5 + "
    "Incorrect * 0.0) / evaluated main questions. 'Not Confirmed' answers are "
    "excluded. This is an AI-assisted estimate, not an objective hiring score, "
    "and must not be used as the sole basis for a hiring decision."
)


class ReportService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm or LLMService()

    def generate_report(self, interview_id: int) -> InterviewReport:
        interview = self.db.get(Interview, interview_id)
        if interview is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")

        questions: list[Question] = (
            self.db.query(Question)
            .filter(Question.interview_id == interview_id)
            .order_by(Question.question_number)
            .all()
        )

        main_evaluations: list[dict] = []
        question_analysis: list[QuestionReportItem] = []
        for question in questions:
            main_answers: list[Answer] = (
                self.db.query(Answer)
                .filter(Answer.question_id == question.id, Answer.is_followup.is_(False))
                .order_by(Answer.created_at.asc())
                .all()
            )
            main_ev = (
                self.db.query(Evaluation)
                .filter(Evaluation.answer_id.in_([a.id for a in main_answers]))
                .order_by(Evaluation.created_at.desc())
                .first()
                if main_answers
                else None
            )
            classification = main_ev.classification if main_ev else "Not Answered"
            score = main_ev.score if main_ev else 0.0
            main_evaluations.append(
                {
                    "classification": classification,
                    "score": score,
                    "has_eval": main_ev is not None,
                }
            )

            followup_items: list[dict] = []
            followups = question.followups or []
            for fu in followups:
                fu_answers: list[Answer] = (
                    self.db.query(Answer)
                    .filter(Answer.followup_id == fu.id)
                    .order_by(Answer.created_at.asc())
                    .all()
                )
                fu_ev = (
                    self.db.query(Evaluation)
                    .filter(Evaluation.answer_id.in_([a.id for a in fu_answers]))
                    .order_by(Evaluation.created_at.desc())
                    .first()
                    if fu_answers
                    else None
                )
                followup_items.append(
                    {
                        "text": fu.text,
                        "classification": fu_ev.classification if fu_ev else "Not Answered",
                        "score": fu_ev.score if fu_ev else 0.0,
                    }
                )

            question_analysis.append(
                QuestionReportItem(
                    question_number=question.question_number,
                    question=question.question,
                    classification=classification,
                    score=score,
                    reason=main_ev.reason if main_ev else "",
                    follow_up_answers=followup_items,
                )
            )

        counts = {
            "Correct": 0,
            "Incorrect": 0,
            "Partially Correct": 0,
            "Not Confirmed": 0,
            "Not Answered": 0,
        }
        evaluated = 0
        for item in main_evaluations:
            if item["has_eval"]:
                counts[item["classification"]] = counts.get(item["classification"], 0) + 1
                evaluated += 1
            else:
                counts["Not Answered"] += 1

        denominator = evaluated or 1
        percentages = {k: round(v / denominator * 100, 1) for k, v in counts.items()}
        performance_score = (
            round(
                (counts["Correct"] * 1.0 + counts["Partially Correct"] * 0.5)
                / denominator,
                3,
            )
            if evaluated
            else None
        )

        visual_stats = self._visual_summary(interview_id)
        context = json.dumps(
            {
                "knowledge_stats": {k: v for k, v in counts.items() if k != "Not Answered"},
                "visual_stats": visual_stats,
                "question_analysis": [q.model_dump() for q in question_analysis],
            },
            ensure_ascii=False,
        )
        section = self.llm.generate_final_report(context)

        report = InterviewReport(
            candidate_name=interview.candidate.name,
            interview_type=interview.interview_type,
            difficulty=interview.difficulty,
            date=interview.started_at or interview.created_at,
            duration_seconds=interview.duration_seconds,
            main_questions_count=interview.main_questions_count,
            follow_up_questions_count=interview.follow_up_questions_count,
            total_questions_asked=interview.total_questions_asked,
            counts=counts,
            percentages=percentages,
            performance_score=performance_score,
            scoring_methodology=SCORING_METHODOLOGY,
            visual_cue_summary=visual_stats,
            section=section.model_dump(),
            question_analysis=question_analysis,
            generated_at=datetime.now(timezone.utc),
        )
        return report

    # ------------------------------------------------------------------
    def _visual_summary(self, interview_id: int) -> dict[str, float]:
        events: list[FaceAnalysisEvent] = (
            self.db.query(FaceAnalysisEvent)
            .filter(FaceAnalysisEvent.interview_id == interview_id)
            .all()
        )
        if not events:
            return {}
        total = len(events)
        summary: dict[str, float] = {}
        for event in events:
            summary[event.category] = summary.get(event.category, 0) + 1
        return {k: round(v / total * 100, 1) for k, v in summary.items()}
