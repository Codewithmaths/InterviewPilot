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
from pathlib import Path

from groq import Groq
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.llm import (
    EvaluationResult,
    FollowUpBatch,
    QuestionBatch,
    ReportSection,
)

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"

MAX_TOKENS = 4000
TEMPERATURE = 0.3


class LLMError(Exception):
    """Raised when the LLM cannot produce a valid response."""


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
    def _chat_json(self, system: str, user: str, model: BaseModel, retries: int = 1) -> dict:
        if self.client is None:
            raise MockLLMError("LLM not configured (mock mode); this path requires a real model.")
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                raw = response.choices[0].message.content or ""
                data = _extract_json_object(raw)
                model.model_validate(data)
                return data
            except (ValidationError, ValueError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
                logger.warning("LLM structured output invalid (attempt %s): %s", attempt + 1, exc)
            except Exception as exc:  # network / rate limit / model errors
                last_error = exc
                logger.warning("LLM call failed (attempt %s): %s", attempt + 1, exc)
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
        data = self._chat_json("You output only valid JSON.", user, QuestionBatch)
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
            return self._mock_evaluation(candidate_answer)
        system = load_prompt("answer_evaluation.txt")
        user = system.format(
            question=question,
            topic=topic,
            difficulty=difficulty,
            expected_answer=expected_answer,
            candidate_answer=candidate_answer,
        )
        data = self._chat_json("You output only valid JSON.", user, EvaluationResult)
        result = EvaluationResult.model_validate(data)
        # Enforce internal consistency: follow-up flags must match classification.
        if result.classification != "Partially Correct":
            result.follow_up_required = False
            result.follow_up_questions = []
        elif result.follow_up_required and not result.follow_up_questions:
            result.follow_up_questions = self.generate_followups(
                question, topic, candidate_answer, result.reason, result.missing_concepts
            )
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
        data = self._chat_json("You output only valid JSON.", user, FollowUpBatch)
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
        data = self._chat_json("You output only valid JSON.", user, ReportSection)
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
    def _mock_evaluation(candidate_answer: str) -> EvaluationResult:
        text = candidate_answer.lower()
        if any(word in text for word in ("not know", "no idea", "i don't know", "dont know", "unsure")):
            return EvaluationResult(
                classification="Not Confirmed",
                score=0.0,
                reason="[MOCK] The transcript does not provide enough evidence to evaluate the answer.",
                missing_concepts=[],
                follow_up_required=False,
                follow_up_questions=[],
            )
        if len(candidate_answer.split()) < 12:
            return EvaluationResult(
                classification="Partially Correct",
                score=0.55,
                reason="[MOCK] The answer shows partial understanding but lacks important detail.",
                missing_concepts=["Elaboration", "Examples", "Depth"],
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
