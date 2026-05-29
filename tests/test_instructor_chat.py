from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.instructor import _build_instructor_prompt
from app.models.schemas import (
    InstructorSessionState,
    MasteryRecord,
    RelationshipType,
    Topic,
    TopicRelationship,
)
from app.ui import app as ui_app
from app.ui.app import _format_chat_history


def test_format_chat_history_supports_tuple_history() -> None:
    history = [
        ("What is a watermark?", "It tracks event-time progress."),
        ("How does it affect late data?", "It helps decide when windows are complete."),
    ]

    assert _format_chat_history(history) == (
        "Learner: What is a watermark?\n"
        "Instructor: It tracks event-time progress.\n"
        "Learner: How does it affect late data?\n"
        "Instructor: It helps decide when windows are complete."
    )


def test_format_chat_history_handles_empty_history() -> None:
    assert _format_chat_history(None) == ""
    assert _format_chat_history([]) == ""


def test_format_chat_history_supports_message_history() -> None:
    history = [
        {"role": "user", "content": "Explain Dataflow windows."},
        {"role": "assistant", "content": "Windows group events by time."},
    ]

    assert _format_chat_history(history) == (
        "Learner: Explain Dataflow windows.\n"
        "Instructor: Windows group events by time."
    )


def test_build_instructor_prompt_includes_history() -> None:
    prompt = _build_instructor_prompt(
        question="What about triggers?",
        topic_id="processing.dataflow.windowing",
        topic_title="Dataflow Windowing",
        available_minutes=30,
        selection_reason="Reinforce low-confidence topic",
        conversation_history="Learner: Explain windows.\nInstructor: Windows group events.",
    )

    assert "Topic: processing.dataflow.windowing" in prompt
    assert "Topic title: Dataflow Windowing" in prompt
    assert "Available study time for this session: 30 minutes" in prompt
    assert "Why this topic was selected: Reinforce low-confidence topic" in prompt
    assert "Conversation so far:" in prompt
    assert "Learner: Explain windows." in prompt
    assert "Learner question: What about triggers?" in prompt


def test_parse_available_minutes_supports_hours_and_minutes() -> None:
    assert ui_app._parse_available_minutes("I have 1 hour 30 minutes today") == 90
    assert ui_app._parse_available_minutes("I have 45 minutes to study") == 45
    assert ui_app._parse_available_minutes("Let's study windowing") is None


class FakeRepo:
    async def list_topics(self) -> list[Topic]:
        return [
            Topic(id="data_engineering", title="Foundations", domain="foundation", sort_order=1),
            Topic(id="topic.a", title="Topic A", domain="analytics", sort_order=10),
            Topic(id="topic.b", title="Topic B", domain="analytics", sort_order=20),
        ]

    async def list_mastery(self, user_id: str) -> list[MasteryRecord]:
        return [
            MasteryRecord(topic_id="data_engineering", title="Foundations", mastery=1.0, confidence=1.0),
            MasteryRecord(topic_id="topic.a", title="Topic A", mastery=0.4, confidence=0.5, attempts=2),
            MasteryRecord(topic_id="topic.b", title="Topic B", mastery=0.1, confidence=0.8, attempts=0),
        ]

    async def list_relationships(
        self,
        relationship_type: RelationshipType | None = None,
    ) -> list[TopicRelationship]:
        if relationship_type == RelationshipType.prerequisite:
            return [
                TopicRelationship(
                    source_topic_id="data_engineering",
                    target_topic_id="topic.a",
                    relationship_type=RelationshipType.prerequisite,
                ),
                TopicRelationship(
                    source_topic_id="data_engineering",
                    target_topic_id="topic.b",
                    relationship_type=RelationshipType.prerequisite,
                ),
            ]
        return []


class FakeInstructorAgent:
    def __init__(self, repo: object) -> None:
        self.repo = repo

    async def answer(
        self,
        question: str,
        topic_id: str | None = None,
        topic_title: str | None = None,
        available_minutes: int | None = None,
        selection_reason: str | None = None,
        conversation_history: str | None = None,
    ) -> str:
        return (
            f"topic={topic_id}; title={topic_title}; minutes={available_minutes}; "
            f"reason={selection_reason}; question={question}"
        )


@pytest.mark.asyncio
async def test_instructor_chat_asks_for_time_before_selecting_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_repo() -> FakeRepo:
        return FakeRepo()

    monkeypatch.setattr(ui_app, "repo", fake_repo)

    history, state, topic_status, quiz_topic, cleared = await ui_app.instructor_chat(
        "What should I study?",
        [],
        None,
    )

    assert history[-1]["role"] == "assistant"
    assert "How much time do you have" in str(history[-1]["content"])
    assert topic_status == "No active instructor topic yet."
    assert quiz_topic == ""
    assert cleared == ""
    assert InstructorSessionState(**state).selected_topic_id is None


@pytest.mark.asyncio
async def test_instructor_chat_selects_topic_and_autofills_quiz(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_repo() -> FakeRepo:
        return FakeRepo()

    monkeypatch.setattr(ui_app, "repo", fake_repo)
    monkeypatch.setattr(ui_app, "InstructorAgent", FakeInstructorAgent)
    monkeypatch.setattr(
        ui_app,
        "get_settings",
        lambda: SimpleNamespace(app_user_id="default-user"),
    )

    history, state, topic_status, quiz_topic, cleared = await ui_app.instructor_chat(
        "I have 30 minutes to study",
        [],
        None,
    )

    session = InstructorSessionState(**state)
    assert session.available_minutes == 30
    assert session.selected_topic_id == "topic.a"
    assert session.selected_topic_title == "Topic A"
    assert session.selection_reason == "Reinforce low-confidence topic"
    assert quiz_topic == "topic.a"
    assert cleared == ""
    assert "Current topic: **Topic A**" in topic_status
    assert "I've selected **Topic A**" in str(history[-1]["content"])


@pytest.mark.asyncio
async def test_make_quiz_prefers_instructor_session_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class FakeQuizAgent:
        def __init__(self, repo: object) -> None:
            self.repo = repo

        async def generate(self, topic_id: str):  # type: ignore[no-untyped-def]
            captured["topic_id"] = topic_id
            return SimpleNamespace(question="Q", choices=["A"], topic_id=topic_id)

    async def fake_repo() -> FakeRepo:
        return FakeRepo()

    monkeypatch.setattr(ui_app, "repo", fake_repo)
    monkeypatch.setattr(ui_app, "QuizAgent", FakeQuizAgent)

    question, choices_update, quiz_state = await ui_app.make_quiz(
        "",
        InstructorSessionState(selected_topic_id="topic.a").model_dump(),
    )

    assert captured["topic_id"] == "topic.a"
    assert question == "Q"
    assert quiz_state.topic_id == "topic.a"
