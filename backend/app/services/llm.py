"""LLM service built on the Groq API.

All prompts are stored in app/ai/prompts/ and rendered with str.format.
Structured output is validated with Pydantic and retried once on failure.

A clearly marked TEMPORARY DEVELOPMENT MOCK is used when no valid GROQ_API_KEY
is configured (or LLM_MOCK_MODE=true), so the rest of the platform remains
testable offline.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from groq import Groq
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.llm import (
    EvaluationResult,
    FollowUpBatch,
    MetricScore,
    QuestionBatch,
    ReportSection,
)

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"

MAX_TOKENS = 4000
TEMPERATURE = 0.3
QUESTION_MAX_TOKENS = 4000
EVALUATION_MAX_TOKENS = 1000
FOLLOWUP_MAX_TOKENS = 500
REPORT_MAX_TOKENS = 1500

# Groq free-tier limits are mostly short per-minute windows; ride through
# bursts by waiting for the Retry-After window instead of failing instantly.
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_MAX_WAIT_SECONDS = 30.0


class LLMError(Exception):
    """Raised when the LLM cannot produce a valid response."""


class LLMRateLimitError(LLMError):
    """Raised when Groq rejects a request because the account is rate limited."""


class MockLLMError(Exception):
    """Raised when mock mode is required but not available."""


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_json_object(raw: str) -> dict:
    text = _strip_code_fence(raw)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        raise ValueError("JSON root is not an object")
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _parse_duration_seconds(raw: object) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        # Groq uses durations such as "1m5.5s" and "185ms".
        match = re.fullmatch(
            r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?",
            str(raw or "").strip(),
        )
        if not match:
            return None
        return (
            float(match.group(1) or 0) * 60
            + float(match.group(2) or 0)
            + float(match.group(3) or 0) / 1000
        )


def _retry_after_seconds(exc: Exception) -> float:
    """Best-effort wait time from Groq's rate-limit headers (capped)."""
    response = getattr(exc, "response", None)
    headers = {
        str(key).lower(): str(value)
        for key, value in (getattr(response, "headers", None) or {}).items()
    }
    remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
    remaining_requests = headers.get("x-ratelimit-remaining-requests")
    try:
        token_limit_hit = remaining_tokens is not None and float(remaining_tokens) <= 0
    except ValueError:
        token_limit_hit = False
    try:
        request_limit_hit = remaining_requests is not None and float(remaining_requests) <= 0
    except ValueError:
        request_limit_hit = False

    if token_limit_hit:
        raw = headers.get("x-ratelimit-reset-tokens")
    elif request_limit_hit:
        raw = headers.get("retry-after") or headers.get("x-ratelimit-reset-requests")
    else:
        raw = headers.get("retry-after") or headers.get("x-ratelimit-reset-tokens")

    wait = _parse_duration_seconds(raw)
    if wait is None:
        retry_match = re.search(
            r"(?:try again in|retry after)\s+((?:\d+(?:\.\d+)?m)?(?:\d+(?:\.\d+)?s)?)",
            str(exc),
            re.IGNORECASE,
        )
        if retry_match:
            wait = _parse_duration_seconds(retry_match.group(1))
        else:
            wait = 5.0
    if wait is None:
        wait = 5.0
    return max(0.25, min(wait, RATE_LIMIT_MAX_WAIT_SECONDS))


class LLMService:
    """Wraps Groq chat completions with schema-validated output."""

    def __init__(self, settings: Settings | None = None) -> None:
        from app.core.config import get_settings

        self.settings = settings or get_settings()
        self.mock_mode = self.settings.LLM_MOCK_MODE or not self.settings.GROQ_API_KEY
        self.client: Groq | None = None
        if not self.mock_mode:
            self.client = Groq(api_key=self.settings.GROQ_API_KEY)
        if self.mock_mode:
            logger.warning(
                "LLM running in TEMPORARY DEVELOPMENT MOCK mode "
                "(no valid GROQ_API_KEY configured or LLM_MOCK_MODE=true)."
            )

    # ------------------------------------------------------------------
    # Low-level chat + JSON decode with retry
    # ------------------------------------------------------------------
    def _chat_json(
        self,
        system: str,
        user: str,
        model: BaseModel,
        retries: int = 1,
        max_tokens: int = MAX_TOKENS,
    ) -> dict:
        if self.client is None:
            raise MockLLMError("LLM not configured (mock mode); this path requires a real model.")
        last_error: Exception | None = None
        output_attempts = 0
        rate_limit_attempts = 0
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=max_tokens,
                )
                raw = response.choices[0].message.content or ""
                data = _extract_json_object(raw)
                model.model_validate(data)
                return data
            except (ValidationError, ValueError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
                output_attempts += 1
                logger.warning("LLM structured output invalid (attempt %s): %s", output_attempts, exc)
                if output_attempts > retries:
                    break
            except Exception as exc:  # network / rate limit / model errors
                message = str(exc).lower()
                if getattr(exc, "status_code", None) == 429 or "rate_limit_exceeded" in message:
                    rate_limit_attempts += 1
                    if rate_limit_attempts > RATE_LIMIT_RETRIES:
                        raise LLMRateLimitError(
                            "Groq rate limit reached. Please try again later."
                        ) from exc
                    wait = _retry_after_seconds(exc)
                    logger.warning(
                        "Groq rate limit hit; retrying in %.1f s (%s/%s).",
                        wait,
                        rate_limit_attempts,
                        RATE_LIMIT_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                last_error = exc
                output_attempts += 1
                logger.warning("LLM call failed (attempt %s): %s", output_attempts, exc)
                if output_attempts > retries:
                    break
        raise LLMError(f"LLM could not produce valid structured output: {last_error}")

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------
    def generate_questions(
        self,
        interview_type: str,
        difficulty: str,
        num_questions: int,
        candidate_name: str,
        job_description: str | None = None,
    ) -> QuestionBatch:
        if self.mock_mode:
            return self._mock_questions(interview_type, difficulty, num_questions)
        system = load_prompt("question_generation.txt")
        jd_instructions = ""
        if job_description and job_description.strip():
            jd_instructions = (
                "The questions MUST be aligned with the following job description. "
                "Do not fabricate skills not present in it:\n"
                + job_description.strip()
            )
        else:
            jd_instructions = "No job description provided. Use standard questions for the interview type."
        user = system.format(
            interview_type=interview_type,
            difficulty=difficulty,
            num_questions=num_questions,
            candidate_name=candidate_name,
            job_description_instructions=jd_instructions,
        )
        data = self._chat_json(
            "You output only valid JSON.",
            user,
            QuestionBatch,
            max_tokens=QUESTION_MAX_TOKENS,
        )
        return QuestionBatch.model_validate(data)

    def evaluate_answer(
        self,
        question: str,
        topic: str,
        difficulty: str,
        expected_answer: str,
        candidate_answer: str,
    ) -> EvaluationResult:
        if self.mock_mode:
            return self._mock_evaluation(candidate_answer, question)
        system = load_prompt("answer_evaluation.txt")
        user = system.format(
            question=question,
            topic=topic,
            difficulty=difficulty,
            expected_answer=expected_answer,
            candidate_answer=candidate_answer,
        )
        data = self._chat_json(
            "You output only valid JSON.",
            user,
            EvaluationResult,
            max_tokens=EVALUATION_MAX_TOKENS,
        )
        result = EvaluationResult.model_validate(data)
        # Enforce internal consistency: follow-up flags must match classification.
        if result.classification != "Partially Correct":
            result.follow_up_required = False
            result.follow_up_questions = []
        elif result.follow_up_required and not result.follow_up_questions:
            result.follow_up_questions = self.generate_followups(
                question, topic, candidate_answer, result.reason, result.missing_concepts
            )
        if not result.metrics:
            result.metrics = self._fallback_metrics(result.score)
        return result

    def generate_followups(
        self,
        question: str,
        topic: str,
        candidate_answer: str,
        reason: str,
        missing_concepts: list[str],
    ) -> list[str]:
        if self.mock_mode:
            return self._mock_followups(missing_concepts)
        system = load_prompt("followup_generation.txt")
        user = system.format(
            question=question,
            topic=topic,
            candidate_answer=candidate_answer,
            reason=reason,
            missing_concepts=json.dumps(missing_concepts),
        )
        data = self._chat_json(
            "You output only valid JSON.",
            user,
            FollowUpBatch,
            max_tokens=FOLLOWUP_MAX_TOKENS,
        )
        return FollowUpBatch.model_validate(data).follow_up_questions

    def generate_final_report(self, context: str) -> ReportSection:
        if self.mock_mode:
            return ReportSection(
                strengths=["Demonstrated engagement during the interview."],
                weaknesses=["Evaluation unavailable in mock mode."],
                missing_concepts=["Depends on actual answers."],
                recommended_study_areas=["Review the missing concepts identified during the interview."],
                summary_note=(
                    "This report was produced in TEMPORARY DEVELOPMENT MOCK mode. "
                    "It is an AI-assisted estimate and not a definitive hiring decision."
                ),
            )
        system = load_prompt("final_report.txt")
        user = system + "\n\nInterview context:\n" + context
        data = self._chat_json(
            "You output only valid JSON.",
            user,
            ReportSection,
            max_tokens=REPORT_MAX_TOKENS,
        )
        return ReportSection.model_validate(data)

    # ------------------------------------------------------------------
    # TEMPORARY DEVELOPMENT MOCK implementations (offline/test fallback)
    # ------------------------------------------------------------------
    TOPIC_BANK: dict[str, list[str]] = {
        "Python": [
            "Python Data Structures", "Object-Oriented Programming", "Python Decorators",
            "Generators and Iterators", "Exception Handling", "Python Standard Library",
            "Concurrency in Python", "Python Virtual Environments",
        ],
        "Machine Learning": [
            "Supervised Learning", "Model Evaluation", "Feature Engineering",
            "Overfitting and Regularization", "Gradient Descent", "Ensemble Methods",
            "Classification Metrics", "Train/Test Splitting",
        ],
        "Data Science": [
            "Data Cleaning", "Exploratory Data Analysis", "Statistical Significance",
            "Pandas", "Data Visualization", "Sampling Methods", "Hypothesis Testing",
            "Feature Scaling",
        ],
        "SQL": [
            "Joins", "Aggregation and Grouping", "Window Functions", "Indexing",
            "Query Optimization", "Normalization", "Subqueries", "Transactions",
        ],
        "Software Engineering": [
            "Design Patterns", "System Design", "Version Control", "Testing and TDD",
            "API Design", "Microservices", "CI/CD", "Code Review",
        ],
        "Technical": [
            "Algorithms", "Data Structures", "Networking Basics", "Operating Systems",
            "Databases", "System Design", "Security Basics", "Software Testing",
        ],
        "Behavioral": [
            "Teamwork", "Conflict Resolution", "Time Management", "Leadership",
            "Adaptability", "Communication", "Problem Solving", "Ownership",
        ],
        "HR": [
            "Company Fit", "Career Goals", "Strengths and Weaknesses", "Motivation",
            "Professional Experience", "Team Culture", "Remote Work", "Growth Plan",
        ],
        "Custom": [
            "General Experience", "Problem Solving", "Technical Depth", "Communication",
            "Project Experience", "Domain Knowledge", "Learning Agility", "Collaboration",
        ],
    }

    def _mock_questions(self, interview_type: str, difficulty: str, num_questions: int) -> QuestionBatch:
        topics = self.TOPIC_BANK.get(interview_type, self.TOPIC_BANK["Custom"])
        questions: list = []
        for i in range(num_questions):
            topic = topics[i % len(topics)]
            questions.append(
                {
                    "question_number": i + 1,
                    "question": (
                        f"[MOCK] {interview_type} question {i + 1} about {topic} "
                        f"at {difficulty} difficulty. Replace with real Groq output when "
                        "GROQ_API_KEY is configured."
                    ),
                    "expected_answer": (
                        f"Reference answer: a correct response should explain the core ideas of {topic} "
                        "and demonstrate practical understanding."
                    ),
                    "topic": topic,
                    "difficulty": difficulty,
                }
            )
        return QuestionBatch.model_validate({"questions": questions})

    @staticmethod
    def _fallback_metrics(score: float) -> list[MetricScore]:
        return [
            MetricScore(name="Accuracy", score=score),
            MetricScore(name="Completeness", score=score),
            MetricScore(name="Clarity", score=score),
        ]

    @staticmethod
    def _mock_evaluation(candidate_answer: str, question: str = "") -> EvaluationResult:
        text = candidate_answer.lower()
        if any(word in text for word in ("not know", "no idea", "i don't know", "dont know", "unsure")):
            return EvaluationResult(
                classification="Not Confirmed",
                score=0.0,
                reason="[MOCK] The transcript does not provide enough evidence to evaluate the answer.",
                missing_concepts=[],
                metrics=[
                    MetricScore(name="Accuracy", score=0.0, note="[MOCK] No evidence provided."),
                    MetricScore(name="Completeness", score=0.0, note="[MOCK] No evidence provided."),
                    MetricScore(name="Clarity", score=0.0, note="[MOCK] No evidence provided."),
                ],
                follow_up_required=False,
                follow_up_questions=[],
            )
        if len(candidate_answer.split()) < 12:
            return EvaluationResult(
                classification="Partially Correct",
                score=0.55,
                reason="[MOCK] The answer shows partial understanding but lacks important detail.",
                missing_concepts=["Elaboration", "Examples", "Depth"],
                metrics=[
                    MetricScore(name="Accuracy", score=0.7),
                    MetricScore(name="Completeness", score=0.4, note="[MOCK] Important detail missing."),
                    MetricScore(name="Clarity", score=0.6),
                    MetricScore(name="Depth", score=0.4, note="[MOCK] Lacks a concrete example."),
                ],
                follow_up_required=True,
                follow_up_questions=[
                    "Can you elaborate with a concrete example?",
                    "What is the most important detail you missed?",
                    "How would you apply this in a real scenario?",
                ],
            )
        return EvaluationResult(
            classification="Correct",
            score=0.9,
            reason="[MOCK] The answer is complete and demonstrates a solid understanding.",
            missing_concepts=[],
            metrics=[
                MetricScore(name="Accuracy", score=0.9),
                MetricScore(name="Completeness", score=0.9),
                MetricScore(name="Clarity", score=0.9),
                MetricScore(name="Depth", score=0.85),
            ],
            follow_up_required=False,
            follow_up_questions=[],
        )

    @staticmethod
    def _mock_followups(missing_concepts: list[str]) -> list[str]:
        concepts = missing_concepts or ["the core concept"]
        return [
            f"[MOCK] Could you explain the relationship between these ideas and {concepts[0]}?",
            f"[MOCK] What is the most common mistake people make regarding {concepts[0]}?",
            f"[MOCK] How would you apply {concepts[0]} to solve a real problem?",
        ][:3]
