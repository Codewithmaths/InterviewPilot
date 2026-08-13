"""REST API routes for interviews, questions, answers, evaluations, follow-ups."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.entities import Answer, FollowUpQuestion
from app.schemas.interview import (
    AnswerCreate,
    CandidateQuestionOut,
    InterviewCreate,
    InterviewHistory,
    InterviewReport,
    InterviewSummary,
    QuestionOut,
    interview_to_summary,
)
from app.services.evaluation import EvaluationService
from app.services.interview import InterviewService, StateTransitionError
from app.services.llm import LLMError, LLMRateLimitError
from app.services.report import ReportService
from app.websocket.events import WSEventType, build_message
from app.websocket.manager import manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/interviews", tags=["interviews"])


def _state_error(exc: StateTransitionError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


def _llm_error(exc: LLMError) -> HTTPException:
    if isinstance(exc, LLMRateLimitError):
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Groq API rate limit reached. Please try again later, or enable "
            "LLM_MOCK_MODE=true for local UI testing.",
        )
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The AI service is temporarily unavailable. Please try again later.",
    )


# ---------------------------------------------------------------------------
@router.post("", response_model=InterviewSummary, status_code=status.HTTP_201_CREATED)
async def create_interview(
    data: InterviewCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> InterviewSummary:
    service = InterviewService(db)
    from app.core.config import get_settings

    settings = get_settings()
    origin = request.headers.get("origin")
    base_url = (
        origin
        if origin and origin.rstrip("/") in settings.cors_origin_list
        else settings.FRONTEND_URL
    ).rstrip("/")
    try:
        interview = await run_in_threadpool(service.create_interview, data, base_url)
    except LLMError as exc:
        raise _llm_error(exc) from exc
    return interview_to_summary(interview)


@router.get("", response_model=list[InterviewSummary])
async def list_interviews(db: Session = Depends(get_db)) -> list[InterviewSummary]:
    service = InterviewService(db)
    interviews = await run_in_threadpool(service.list_interviews)
    return [interview_to_summary(i) for i in interviews]


@router.get("/room/{room_code}", response_model=InterviewSummary)
async def get_by_room(room_code: str, db: Session = Depends(get_db)) -> InterviewSummary:
    service = InterviewService(db)
    interview = await run_in_threadpool(service.get_by_room, room_code)
    return interview_to_summary(interview)


@router.get("/{interview_id}", response_model=InterviewSummary)
async def get_interview(interview_id: int, db: Session = Depends(get_db)) -> InterviewSummary:
    service = InterviewService(db)
    interview = await run_in_threadpool(service.get, interview_id)
    return interview_to_summary(interview)


@router.post("/{interview_id}/start", response_model=InterviewSummary)
async def start_interview(interview_id: int, db: Session = Depends(get_db)) -> InterviewSummary:
    service = InterviewService(db)
    try:
        interview = await run_in_threadpool(service.start, interview_id)
    except StateTransitionError as exc:
        raise _state_error(exc)
    await manager.broadcast(
        interview_id,
        build_message(WSEventType.INTERVIEW_STARTED, {}, interview_id),
    )
    if interview.current_question_id is not None and interview.current_question_index is not None:
        await manager.broadcast(
            interview_id,
            build_message(
                WSEventType.QUESTION_CHANGED,
                {
                    "question_number": interview.current_question_index,
                    "question_id": interview.current_question_id,
                },
                interview_id,
            ),
        )
    return interview_to_summary(interview)


@router.post("/{interview_id}/end", response_model=InterviewSummary)
async def end_interview(interview_id: int, db: Session = Depends(get_db)) -> InterviewSummary:
    service = InterviewService(db)
    interview = await run_in_threadpool(service.end, interview_id)
    await manager.broadcast(
        interview_id,
        build_message(WSEventType.INTERVIEW_ENDED, {}, interview_id),
    )
    return interview_to_summary(interview)


# ---------------------------------------------------------------------------
@router.get("/{interview_id}/questions", response_model=list[QuestionOut])
async def list_questions(interview_id: int, db: Session = Depends(get_db)) -> list[QuestionOut]:
    service = InterviewService(db)
    questions = await run_in_threadpool(service.get_questions, interview_id)
    return [QuestionOut.model_validate(q) for q in questions]


@router.get("/{interview_id}/candidate/questions", response_model=list[CandidateQuestionOut])
async def list_candidate_questions(
    interview_id: int, db: Session = Depends(get_db)
) -> list[CandidateQuestionOut]:
    """Return question text without interviewer-only expected answers."""
    service = InterviewService(db)
    questions = await run_in_threadpool(service.get_questions, interview_id)
    return [CandidateQuestionOut.model_validate(q) for q in questions]


@router.post("/{interview_id}/question/next", response_model=QuestionOut)
async def next_question(interview_id: int, db: Session = Depends(get_db)) -> QuestionOut:
    service = InterviewService(db)
    try:
        question = await run_in_threadpool(service.next_question, interview_id)
    except StateTransitionError as exc:
        raise _state_error(exc)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No more questions")
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.QUESTION_CHANGED,
            {"question_number": question.question_number, "question_id": question.id},
            interview_id,
        ),
    )
    return QuestionOut.model_validate(question)


@router.post("/{interview_id}/question/repeat", response_model=QuestionOut)
async def repeat_question(interview_id: int, db: Session = Depends(get_db)) -> QuestionOut:
    service = InterviewService(db)
    try:
        question = await run_in_threadpool(service.repeat_question, interview_id)
    except StateTransitionError as exc:
        raise _state_error(exc)
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.QUESTION_CHANGED,
            {"question_number": question.question_number, "question_id": question.id},
            interview_id,
        ),
    )
    return QuestionOut.model_validate(question)


@router.post("/{interview_id}/question/skip", response_model=QuestionOut)
async def skip_question(interview_id: int, db: Session = Depends(get_db)) -> QuestionOut:
    service = InterviewService(db)
    try:
        question = await run_in_threadpool(service.skip_question, interview_id)
    except StateTransitionError as exc:
        raise _state_error(exc)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No more questions")
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.QUESTION_CHANGED,
            {"question_number": question.question_number, "question_id": question.id},
            interview_id,
        ),
    )
    return QuestionOut.model_validate(question)


@router.post("/{interview_id}/question/{question_number}", response_model=QuestionOut)
async def move_to_question(
    interview_id: int, question_number: int, db: Session = Depends(get_db)
) -> QuestionOut:
    service = InterviewService(db)
    try:
        question = await run_in_threadpool(service.move_to_question, interview_id, question_number)
    except StateTransitionError as exc:
        raise _state_error(exc)
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.QUESTION_CHANGED,
            {"question_number": question_number, "question_id": question.id},
            interview_id,
        ),
    )
    return QuestionOut.model_validate(question)


# ---------------------------------------------------------------------------
@router.get("/{interview_id}/history", response_model=InterviewHistory)
async def get_history(interview_id: int, db: Session = Depends(get_db)) -> InterviewHistory:
    service = InterviewService(db)
    history = await run_in_threadpool(service.get_history, interview_id)
    return InterviewHistory(items=history)


# ---------------------------------------------------------------------------
@router.post("/{interview_id}/answers")
async def create_answer(
    interview_id: int, data: AnswerCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Store a candidate answer (main or follow-up) and evaluate it."""
    service = EvaluationService(db)
    try:
        result = await run_in_threadpool(
            service.evaluate_main_answer if data.question_id else service.evaluate_followup_answer,
            interview_id,
            data.question_id or data.followup_id,
            data.transcript,
            data.duration_seconds,
        )
    except LLMError as exc:
        raise _llm_error(exc) from exc
    payload = result["payload"]
    await manager.broadcast(
        interview_id, build_message(WSEventType.EVALUATION_COMPLETED, payload, interview_id)
    )
    return {
        "answer_id": payload["answer_id"],
        "classification": payload["classification"],
        "score": payload["score"],
        "reason": payload["reason"],
        "missing_concepts": payload["missing_concepts"],
        "metrics": payload["metrics"],
        "follow_up_required": payload["follow_up_required"],
        "follow_up_questions": payload["follow_up_questions"],
    }


@router.get("/{interview_id}/followups", response_model=list[dict[str, Any]])
async def list_followups(interview_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    service = InterviewService(db)
    questions = await run_in_threadpool(service.get_questions, interview_id)
    result: list[dict[str, Any]] = []
    for q in questions:
        fups: list[FollowUpQuestion] = (
            db.query(FollowUpQuestion)
            .filter(FollowUpQuestion.question_id == q.id)
            .order_by(FollowUpQuestion.followup_number)
            .all()
        )
        for fu in fups:
            result.append(
                {
                    "id": fu.id,
                    "question_id": fu.question_id,
                    "followup_number": fu.followup_number,
                    "text": fu.text,
                    "answered": (
                        db.query(Answer)
                        .filter(Answer.followup_id == fu.id)
                        .first()
                        is not None
                    ),
                }
            )
    return result


@router.post("/{interview_id}/followups/{followup_id}/select")
async def select_followup(
    interview_id: int, followup_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    service = EvaluationService(db)
    followup = await run_in_threadpool(service.select_followup, interview_id, followup_id)
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.FOLLOWUP_SELECTED,
            {"followup_id": followup.id, "text": followup.text},
            interview_id,
        ),
    )
    return {"followup_id": followup.id, "text": followup.text}


@router.post("/{interview_id}/followups/{followup_id}/answer")
async def answer_followup(
    interview_id: int, followup_id: int, data: AnswerCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    service = EvaluationService(db)
    try:
        result = await run_in_threadpool(
            service.evaluate_followup_answer,
            interview_id,
            followup_id,
            data.transcript,
            data.duration_seconds,
        )
    except LLMError as exc:
        raise _llm_error(exc) from exc
    await manager.broadcast(
        interview_id,
        build_message(WSEventType.EVALUATION_COMPLETED, result["payload"], interview_id),
    )
    return {
        "answer_id": result["payload"]["answer_id"],
        "classification": result["payload"]["classification"],
        "score": result["payload"]["score"],
        "reason": result["payload"]["reason"],
        "metrics": result["payload"]["metrics"],
    }


# ---------------------------------------------------------------------------
@router.get("/{interview_id}/report", response_model=InterviewReport)
async def get_report(
    interview_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
) -> InterviewReport:
    """Return the stored report from the database, or generate and persist it."""
    service = ReportService(db)
    try:
        if not refresh:
            saved = await run_in_threadpool(service.get_saved_report, interview_id)
            if saved is not None:
                return saved
        return await run_in_threadpool(service.generate_report, interview_id)
    except LLMError as exc:
        raise _llm_error(exc) from exc


@router.get("/{interview_id}/state")
async def get_state(interview_id: int, db: Session = Depends(get_db)) -> dict[str, str | int | None]:
    service = InterviewService(db)
    interview = await run_in_threadpool(service.get, interview_id)
    return {
        "state": interview.status,
        "current_question_index": interview.current_question_index,
        "main_questions": interview.main_questions_count,
    }

@router.post("/{interview_id}/state")
async def set_state(interview_id: int, body: dict, db: Session = Depends(get_db)) -> dict[str, str | int | None]:
    """Advance the interview state machine (validated against allowed transitions)."""
    target = (body.get("to_state") or "").upper()
    service = InterviewService(db)
    try:
        interview = await run_in_threadpool(service.transition, interview_id, target)
    except StateTransitionError as exc:
        raise _state_error(exc)
    await manager.broadcast(
        interview_id,
        build_message(
            WSEventType.STATE_CHANGED,
            {"to": target, "from": interview.status},
            interview_id,
        ),
    )
    return {
        "state": interview.status,
        "current_question_index": interview.current_question_index,
        "main_questions": interview.main_questions_count,
    }

