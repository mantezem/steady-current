from __future__ import annotations

from app.agents.instructor import _build_instructor_prompt
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
        conversation_history="Learner: Explain windows.\nInstructor: Windows group events.",
    )

    assert "Topic: processing.dataflow.windowing" in prompt
    assert "Conversation so far:" in prompt
    assert "Learner: Explain windows." in prompt
    assert "Learner question: What about triggers?" in prompt
