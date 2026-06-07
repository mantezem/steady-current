from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.quiz import QuizAgent, _build_quiz_prompt, _parse_quiz_output, _target_difficulty
from app.models.schemas import MasteryRecord, Topic


def test_parse_quiz_output_overrides_stale_topic_id() -> None:
    question = _parse_quiz_output(
        {
            "topic_id": "processing.dataflow.windowing",
            "question": "How does partitioning reduce scanned data?",
            "choices": ["By pruning partitions", "By disabling slots"],
            "correct_answer": "By pruning partitions",
            "explanation": "Partition filters reduce the amount of data scanned.",
        },
        "storage.bigquery.partitioning",
    )

    assert question.topic_id == "storage.bigquery.partitioning"


def test_parse_quiz_output_sets_missing_topic_id() -> None:
    question = _parse_quiz_output(
        {
            "question": "What is allowed lateness?",
            "choices": ["A late-data grace period", "A storage class"],
            "correct_answer": "A late-data grace period",
            "explanation": "It permits corrections after the initial window firing.",
        },
        "processing.dataflow.windowing",
    )

    assert question.topic_id == "processing.dataflow.windowing"


def test_target_difficulty_raises_floor_for_beginner_topics() -> None:
    topic = Topic(id="topic.a", title="Topic A", domain="analytics", difficulty="beginner")

    assert _target_difficulty(topic, None) == "intermediate"


def test_target_difficulty_pushes_to_advanced_for_strong_mastery() -> None:
    topic = Topic(id="topic.a", title="Topic A", domain="analytics", difficulty="intermediate")
    mastery = MasteryRecord(
        topic_id="topic.a",
        title="Topic A",
        mastery=0.8,
        confidence=0.4,
        attempts=4,
    )

    assert _target_difficulty(topic, mastery) == "advanced"


def test_build_quiz_prompt_includes_difficulty_and_mastery_context() -> None:
    topic = Topic(
        id="storage.bigquery.partitioning",
        title="BigQuery Partitioning",
        domain="analytics",
        description="Partition strategies for pruning, cost control, and maintainability.",
        difficulty="intermediate",
    )
    mastery = MasteryRecord(
        topic_id=topic.id,
        title=topic.title,
        mastery=0.6,
        confidence=0.3,
        attempts=2,
    )

    prompt = _build_quiz_prompt(topic.id, topic, mastery)

    assert "Required question difficulty: advanced" in prompt
    assert "Learner calibration: mastery=60%, confidence=30%, attempts=2" in prompt
    assert "Topic description: Partition strategies for pruning, cost control, and maintainability." in prompt


class FakeRepo:
    async def get_topic(self, topic_id: str) -> Topic:
        return Topic(
            id=topic_id,
            title="BigQuery Partitioning",
            domain="analytics",
            description="Partition strategies for pruning, cost control, and maintainability.",
            difficulty="intermediate",
        )

    async def list_mastery(self, user_id: str) -> list[MasteryRecord]:
        return []


@pytest.mark.asyncio
async def test_quiz_agent_fallback_uses_topic_aware_harder_question(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agents.quiz.get_settings",
        lambda: SimpleNamespace(openai_api_key=None, openai_model="gpt-4.1-mini", app_user_id="default-user"),
    )

    question = await QuizAgent(FakeRepo()).generate("storage.bigquery.partitioning")

    assert "scan cost" in question.question
    assert any("Cluster the partitioned table by `customer_id`" in choice for choice in question.choices)
