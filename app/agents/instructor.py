from __future__ import annotations

from pathlib import Path

from agents import Agent, Runner, flush_traces, trace

from app.agents.tools import search_docs
from app.db.repositories import LearningRepository
from app.retrieval.service import RetrievalService
from app.utils.config import get_settings


def _build_instructor_prompt(
    question: str,
    topic_id: str | None = None,
    topic_title: str | None = None,
    available_minutes: int | None = None,
    selection_reason: str | None = None,
    conversation_history: str | None = None,
) -> str:
    sections = [f"Topic: {topic_id or 'general'}"]
    if topic_title:
        sections.append(f"Topic title: {topic_title}")
    if available_minutes is not None:
        sections.append(f"Available study time for this session: {available_minutes} minutes")
    if selection_reason:
        sections.append(f"Why this topic was selected: {selection_reason}")
    if conversation_history:
        sections.append(
            "Conversation so far:\n"
            f"{conversation_history}\n\n"
            "Use this only for continuity and resolving references in the latest question."
        )
    sections.append(f"Learner question: {question}")
    return "\n\n".join(sections)


class InstructorAgent:
    def __init__(self, repo: LearningRepository) -> None:
        self.repo = repo
        self.settings = get_settings()
        instructions = Path("app/prompts/instructor.md").read_text()
        self.agent = Agent(
            name="InstructorAgent",
            instructions=instructions,
            tools=[search_docs],
            model=self.settings.openai_model,
        )

    async def answer(
        self,
        question: str,
        topic_id: str | None = None,
        topic_title: str | None = None,
        available_minutes: int | None = None,
        selection_reason: str | None = None,
        conversation_history: str | None = None,
    ) -> str:
        if not self.settings.openai_api_key:
            retrieval = RetrievalService(self.repo)
            retrieval_query = _build_instructor_prompt(
                question,
                topic_id,
                topic_title,
                available_minutes,
                selection_reason,
                conversation_history,
            )
            chunks = await retrieval.search(retrieval_query, topic_id=topic_id)
            return (
                "OPENAI_API_KEY is not set, so this is a retrieval-only instructor response.\n\n"
                f"{retrieval.format_citations(chunks)}"
            )
        prompt = _build_instructor_prompt(
            question,
            topic_id,
            topic_title,
            available_minutes,
            selection_reason,
            conversation_history,
        )
        with trace(
            "steady-current-instructor",
            group_id="instructor-chat",
            metadata={"topic_id": topic_id or "general"},
        ):
            result = await Runner.run(self.agent, prompt)
        flush_traces()
        return str(result.final_output)
