from __future__ import annotations

import re
from typing import Any

import gradio as gr

from app.agents.evaluator import EvaluationAgent
from app.agents.quiz import QuizAgent
from app.agents.instructor import InstructorAgent
from app.db.connection import get_pool
from app.db.repositories import LearningRepository
from app.models.schemas import InstructorSessionState, QuizQuestion
from app.planner.service import StudyPlanner
from app.utils.config import get_settings


async def repo() -> LearningRepository:
    return LearningRepository(await get_pool())


async def dashboard() -> str:
    settings = get_settings()
    learning_repo = await repo()
    records = await learning_repo.list_mastery(settings.app_user_id)
    weak = [record for record in records if record.mastery < 0.7 and record.topic_id != "data_engineering"]
    readiness = sum(record.mastery for record in records) / max(len(records), 1)
    lines = [f"Domain readiness: {readiness:.0%}", "", "Weak topics:"]
    lines.extend(f"- {record.title}: {record.mastery:.0%}" for record in weak[:8])
    lines.append("")
    lines.append("Mastery:")
    lines.extend(
        f"- {record.title}: {record.mastery:.0%} confidence {record.confidence:.0%}, "
        f"attempts {record.attempts}"
        for record in records
    )
    return "\n".join(lines)


def _chat_content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _format_chat_history(history: list[object] | None, max_turns: int = 8) -> str:
    lines: list[str] = []
    if not history:
        return ""

    recent_history = history[-max_turns:]

    for item in recent_history:
        if isinstance(item, dict):
            role = str(item.get("role", "")).lower()
            content = _chat_content_text(item.get("content"))
            if role == "user" and content:
                lines.append(f"Learner: {content}")
            elif role == "assistant" and content:
                lines.append(f"Instructor: {content}")
            continue

        if isinstance(item, (list, tuple)) and len(item) >= 2:
            learner_message = _chat_content_text(item[0])
            instructor_message = _chat_content_text(item[1])
            if learner_message:
                lines.append(f"Learner: {learner_message}")
            if instructor_message:
                lines.append(f"Instructor: {instructor_message}")

    return "\n".join(lines)


def _session_state(value: dict[str, Any] | InstructorSessionState | None) -> InstructorSessionState:
    if isinstance(value, InstructorSessionState):
        return value
    if isinstance(value, dict):
        return InstructorSessionState(**value)
    return InstructorSessionState()


def _parse_available_minutes(message: str) -> int | None:
    text = message.lower()
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", text)
    minute_match = re.search(r"(\d+)\s*(minutes?|mins?|m)\b", text)
    bare_minutes_match = re.search(r"\b(\d+)\s*(?:min study session|minute study session)\b", text)

    minutes = 0
    matched = False
    if hour_match:
        minutes += int(float(hour_match.group(1)) * 60)
        matched = True
    if minute_match:
        minutes += int(minute_match.group(1))
        matched = True
    if not matched and bare_minutes_match:
        minutes = int(bare_minutes_match.group(1))
        matched = True
    if not matched:
        return None
    return max(minutes, 1)


def _looks_like_time_only_message(message: str) -> bool:
    text = message.strip().lower()
    return bool(re.fullmatch(r"(i have|have|got|around|about|approximately|roughly)?[\s:]*[\d\.\sa-z/,-]+", text))


def _learner_requested_switch(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "switch topic",
            "different topic",
            "another topic",
            "change topic",
            "new topic",
        )
    )


def _learner_ready_for_quiz(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "ready for quiz",
            "ready to quiz",
            "quiz me",
            "start quiz",
            "let's do a quiz",
            "lets do a quiz",
        )
    )


def _learner_requests_another_question(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "another question",
            "next question",
            "one more question",
            "more practice",
            "ask another",
        )
    )


def _topic_status_markdown(state: dict[str, Any] | InstructorSessionState | None) -> str:
    session = _session_state(state)
    if not session.selected_topic_id or not session.selected_topic_title:
        return "No active instructor topic yet."
    status = (
        f"Current topic: **{session.selected_topic_title}**  \n"
        f"Topic ID: `{session.selected_topic_id}`  \n"
        f"Reason: {session.selection_reason or 'Recommended for this session.'}"
    )
    if session.available_minutes is not None:
        status += f"  \nSession time: {session.available_minutes} min"
    if session.active_question is not None:
        status += "  \nQuiz status: awaiting answer"
    elif session.ready_for_quiz:
        status += "  \nQuiz status: ready for another question"
    status += f"  \nMode: {session.mode}"
    return status


def _topic_intro(state: InstructorSessionState) -> str:
    parts = [
        f"I've selected **{state.selected_topic_title}** for this study session.",
        state.selection_reason or "This is the best next topic based on your current progress.",
    ]
    if state.available_minutes is not None:
        parts.append(f"We'll scope this to about {state.available_minutes} minutes.")
    return " ".join(parts)


def _question_markdown(question: QuizQuestion) -> str:
    choices = "\n".join(f"{index}. {choice}" for index, choice in enumerate(question.choices, start=1))
    return (
        f"Quiz question for **{question.topic_id}**:\n\n"
        f"{question.question}\n\n"
        f"{choices}\n\n"
        "Reply in chat with the choice number, letter, or the full answer text."
    )


def _resolve_quiz_answer(message: str, question: QuizQuestion) -> str | None:
    raw = message.strip()
    if not raw:
        return None

    for choice in question.choices:
        if raw.casefold() == choice.casefold():
            return choice

    numeric_match = re.fullmatch(r"(\d+)[\).]?", raw)
    if numeric_match:
        index = int(numeric_match.group(1)) - 1
        if 0 <= index < len(question.choices):
            return question.choices[index]

    letter_match = re.fullmatch(r"([A-Za-z])[\).]?", raw)
    if letter_match:
        index = ord(letter_match.group(1).upper()) - ord("A")
        if 0 <= index < len(question.choices):
            return question.choices[index]

    prefixed_match = re.fullmatch(r"([A-Za-z]|\d+)[\).:\-]\s*(.+)", raw)
    if prefixed_match:
        candidate = prefixed_match.group(2).strip()
        for choice in question.choices:
            if candidate.casefold() == choice.casefold():
                return choice

    return None


async def _start_quiz_question(
    history: list[dict[str, str]],
    session: InstructorSessionState,
    learning_repo: LearningRepository,
) -> tuple[list[dict[str, str]], InstructorSessionState]:
    if not session.selected_topic_id:
        raise ValueError("No active topic is available for quiz generation.")
    question = await QuizAgent(learning_repo).generate(session.selected_topic_id)
    session.active_question = question
    session.mode = "quiz"
    session.ready_for_quiz = False
    history.append({"role": "assistant", "content": _question_markdown(question)})
    return history, session


def _chat_outputs(
    history: list[dict[str, str]],
    session: InstructorSessionState,
    clear_message: str = "",
) -> tuple[list[dict[str, str]], dict[str, Any], str, str]:
    return (history, session.model_dump(), _topic_status_markdown(session), clear_message)


async def instructor_chat(
    message: str,
    history: list[dict[str, str]] | None,
    session_state: dict[str, Any] | InstructorSessionState | None,
) -> tuple[list[dict[str, str]], dict[str, Any], str, str]:
    history = list(history or [])
    session = _session_state(session_state)
    parsed_minutes = _parse_available_minutes(message)
    if session.available_minutes is None and parsed_minutes is not None:
        session.available_minutes = parsed_minutes

    learning_repo = await repo()
    settings = get_settings()
    planner = StudyPlanner(learning_repo)

    if session.available_minutes is None:
        reply = "How much time do you have for this study session? Reply with something like `20 minutes` or `1 hour`."
        history.extend(
            [
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply},
            ]
        )
        return _chat_outputs(history, session, "")

    history.append({"role": "user", "content": message})

    selected_new_topic = False
    if session.selected_topic_id is None or _learner_requested_switch(message):
        recommendation = await planner.recommend_topic(
            settings.app_user_id,
            session.available_minutes,
            exclude_topic_id=session.selected_topic_id if _learner_requested_switch(message) else None,
        )
        if recommendation is None:
            reply = "I couldn't find an unlocked topic to recommend yet. Try taking a quiz first so I can calibrate your current level."
            history.append({"role": "assistant", "content": reply})
            return _chat_outputs(history, session, "")
        session.selected_topic_id = recommendation.topic_id
        session.selected_topic_title = recommendation.title
        session.selection_reason = recommendation.reason
        session.mode = "discussion"
        session.ready_for_quiz = False
        session.active_question = None
        selected_new_topic = True

    if session.mode == "quiz" and session.active_question is not None:
        resolved_answer = _resolve_quiz_answer(message, session.active_question)
        if resolved_answer is None:
            choices = ", ".join(
                f"{index}. {choice}" for index, choice in enumerate(session.active_question.choices, start=1)
            )
            history.append(
                {
                    "role": "assistant",
                    "content": (
                        "I couldn't match that to one of the answer choices. "
                        f"Reply with the choice number, letter, or exact text: {choices}."
                    ),
                }
            )
            return _chat_outputs(history, session, "")
        settings = get_settings()
        result = await EvaluationAgent(learning_repo).evaluate(
            settings.app_user_id,
            session.active_question,
            resolved_answer,
        )
        verdict = "Correct" if result.is_correct else "Incorrect"
        history.append(
            {
                "role": "assistant",
                "content": (
                    f"{verdict}\n\n{result.explanation}\n\n"
                    f"Updated mastery: {result.mastery:.0%}. Confidence: {result.confidence:.0%}.\n\n"
                    "Ask for another question to keep practicing, or ask a follow-up question to return to discussion."
                ),
            }
        )
        session.active_question = None
        session.ready_for_quiz = True
        return _chat_outputs(history, session, "")

    if _learner_ready_for_quiz(message) or (session.mode == "quiz" and _learner_requests_another_question(message)):
        history, session = await _start_quiz_question(history, session, learning_repo)
        return _chat_outputs(history, session, "")

    if session.mode == "quiz" and session.active_question is None:
        session.mode = "discussion"
        session.ready_for_quiz = False

    agent = InstructorAgent(learning_repo)
    prompt_message = (
        "Introduce this topic for the current study session. Explain what to focus on first, "
        "what tradeoffs matter, and which cited docs or labs are worth reading next."
        if selected_new_topic and _looks_like_time_only_message(message)
        else message
    )
    answer = await agent.answer(
        prompt_message,
        session.selected_topic_id,
        session.selected_topic_title,
        session.available_minutes,
        session.selection_reason,
        _format_chat_history(history),
    )
    if selected_new_topic:
        answer = f"{_topic_intro(session)}\n\n{answer}"
        answer += "\n\nAsk follow-up questions when you want more detail, or say `quiz me` when you're ready for practice."
    history.append({"role": "assistant", "content": answer})
    return _chat_outputs(history, session, "")


async def topic_tree() -> str:
    settings = get_settings()
    learning_repo = await repo()
    return await learning_repo.topic_tree_markdown(settings.app_user_id)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Steady Current") as demo:
        gr.Markdown("# Steady Current")
        instructor_session = gr.State(InstructorSessionState().model_dump())

        with gr.Tab("Progress Dashboard"):
            refresh_dashboard = gr.Button("Refresh")
            dashboard_output = gr.Markdown()
            refresh_dashboard.click(fn=dashboard, outputs=dashboard_output)

        with gr.Tab("Instructor Chat"):
            instructor_topic_status = gr.Markdown("No active instructor topic yet.")
            instructor_chatbot = gr.Chatbot(label="Instructor")
            instructor_message = gr.Textbox(
                label="Message",
                placeholder="Example: I have 30 minutes to study. What should I focus on?",
            )
            instructor_send = gr.Button("Send")
            instructor_send.click(
                fn=instructor_chat,
                inputs=[instructor_message, instructor_chatbot, instructor_session],
                outputs=[
                    instructor_chatbot,
                    instructor_session,
                    instructor_topic_status,
                    instructor_message,
                ],
            )
            instructor_message.submit(
                fn=instructor_chat,
                inputs=[instructor_message, instructor_chatbot, instructor_session],
                outputs=[
                    instructor_chatbot,
                    instructor_session,
                    instructor_topic_status,
                    instructor_message,
                ],
            )

        with gr.Tab("Topic Tree"):
            refresh_tree = gr.Button("Refresh")
            tree_output = gr.Markdown()
            refresh_tree.click(fn=topic_tree, outputs=tree_output)

    return demo
