from __future__ import annotations

from app.db.repositories import LearningRepository
from app.models.schemas import EvaluationResult, QuizQuestion


class EvaluationAgent:
    def __init__(self, repo: LearningRepository) -> None:
        self.repo = repo

    async def evaluate(
        self, user_id: str, question: QuizQuestion, selected_answer: str
    ) -> EvaluationResult:
        is_correct = selected_answer == question.correct_answer
        explanation = question.explanation
        record = await self.repo.record_attempt(
            user_id=user_id,
            topic_id=question.topic_id,
            question=question.question,
            answer=selected_answer,
            correct_answer=question.correct_answer,
            is_correct=is_correct,
            explanation=explanation,
        )
        return EvaluationResult(
            is_correct=is_correct,
            explanation=explanation,
            mastery=record.mastery,
            confidence=record.confidence,
        )
