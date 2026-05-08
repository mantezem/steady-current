from __future__ import annotations

from typing import Any

import gradio as gr

from app.agents.evaluator import EvaluationAgent
from app.agents.quiz import QuizAgent
from app.agents.instructor import InstructorAgent
from app.db.connection import get_pool
from app.db.repositories import LearningRepository
from app.models.schemas import QuizQuestion, StudySetup
from app.planner.service import StudyPlanner
from app.utils.config import get_settings


async def repo() -> LearningRepository:
    return LearningRepository(await get_pool())


async def save_setup(timeline: str, preferences: str, strengths: str, weaknesses: str) -> str:
    settings = get_settings()
    learning_repo = await repo()
    await learning_repo.save_preferences(
        settings.app_user_id,
        StudySetup(
            study_timeline=timeline,
            preferences=preferences,
            strengths=strengths,
            weaknesses=weaknesses,
        ),
    )
    planner = StudyPlanner(learning_repo)
    plan = await planner.plan(settings.app_user_id, 60)
    if not plan:
        return "Setup saved. No unlocked weak topics found yet."
    return "Setup saved.\n\n" + "\n".join(
        f"- {item.title}: {item.reason} ({item.estimated_minutes} min)" for item in plan
    )


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


async def instructor_chat(message: str, history: list[object], topic_id: str) -> str:
    learning_repo = await repo()
    agent = InstructorAgent(learning_repo)
    return await agent.answer(message, topic_id or None, _format_chat_history(history))


async def make_quiz(topic_id: str) -> tuple[str, gr.update, QuizQuestion]:
    learning_repo = await repo()
    question = await QuizAgent(learning_repo).generate(topic_id)
    return question.question, gr.update(choices=question.choices, value=None), question


async def submit_answer(question: QuizQuestion, answer: str) -> str:
    if question is None or not answer:
        return "Choose an answer first."
    settings = get_settings()
    learning_repo = await repo()
    result = await EvaluationAgent(learning_repo).evaluate(settings.app_user_id, question, answer)
    verdict = "Correct" if result.is_correct else "Incorrect"
    return (
        f"{verdict}\n\n{result.explanation}\n\n"
        f"Updated mastery: {result.mastery:.0%}. Confidence: {result.confidence:.0%}."
    )


async def topic_tree() -> str:
    settings = get_settings()
    learning_repo = await repo()
    return await learning_repo.topic_tree_markdown(settings.app_user_id)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Steady Current") as demo:
        gr.Markdown("# Steady Current")
        quiz_state = gr.State()

        with gr.Tab("Study Setup"):
            timeline = gr.Textbox(label="Study timeline", placeholder="Example: 8 weeks, 5 hours/week")
            preferences = gr.Textbox(label="Preferences", lines=3)
            strengths = gr.Textbox(label="Known strengths", lines=2)
            weaknesses = gr.Textbox(label="Known weaknesses", lines=2)
            setup_button = gr.Button("Save setup")
            setup_output = gr.Markdown()
            setup_button.click(
                fn=save_setup,
                inputs=[timeline, preferences, strengths, weaknesses],
                outputs=setup_output,
            )

        with gr.Tab("Progress Dashboard"):
            refresh_dashboard = gr.Button("Refresh")
            dashboard_output = gr.Markdown()
            refresh_dashboard.click(fn=dashboard, outputs=dashboard_output)

        with gr.Tab("Instructor Chat"):
            instructor_topic = gr.Textbox(label="Topic ID", placeholder="processing.dataflow.windowing")
            gr.ChatInterface(
                fn=instructor_chat,
                additional_inputs=[instructor_topic],
            )

        with gr.Tab("Quiz"):
            quiz_topic = gr.Textbox(label="Topic ID", value="processing.dataflow.windowing")
            generate_button = gr.Button("Generate question")
            question_text = gr.Markdown()
            choices = gr.Radio(label="Answer", choices=[])
            submit_button = gr.Button("Submit answer")
            quiz_result = gr.Markdown()
            generate_button.click(
                fn=make_quiz,
                inputs=quiz_topic,
                outputs=[question_text, choices, quiz_state],
            )
            submit_button.click(
                fn=submit_answer,
                inputs=[quiz_state, choices],
                outputs=quiz_result,
            )

        with gr.Tab("Topic Tree"):
            refresh_tree = gr.Button("Refresh")
            tree_output = gr.Markdown()
            refresh_tree.click(fn=topic_tree, outputs=tree_output)

    return demo
