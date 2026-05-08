from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agents import Agent, Runner, flush_traces, trace

from app.agents.tools import search_docs
from app.db.repositories import LearningRepository
from app.models.schemas import QuizQuestion
from app.utils.config import get_settings


def _normalize_quiz_payload(data: dict[str, Any], topic_id: str) -> dict[str, Any]:
    data.setdefault("topic_id", topic_id)

    choices = data.get("choices")
    if isinstance(choices, dict):
        data["choices"] = [f"{key}. {value}" for key, value in choices.items()]

        correct_answer = str(data.get("correct_answer", ""))
        if correct_answer in choices:
            data["correct_answer"] = f"{correct_answer}. {choices[correct_answer]}"
        elif len(correct_answer) == 1 and correct_answer.upper() in choices:
            key = correct_answer.upper()
            data["correct_answer"] = f"{key}. {choices[key]}"

    return data


def _parse_quiz_output(output: object, topic_id: str) -> QuizQuestion:
    if isinstance(output, QuizQuestion):
        return output
    if isinstance(output, dict):
        return QuizQuestion(**_normalize_quiz_payload(output, topic_id))

    text = str(output).strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1)
    elif not text.startswith("{"):
        object_match = re.search(r"\{.*\}", text, re.DOTALL)
        if object_match:
            text = object_match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Quiz agent did not return parseable JSON: {str(output)[:500]}") from exc
    return QuizQuestion(**_normalize_quiz_payload(data, topic_id))


class QuizAgent:
    def __init__(self, repo: LearningRepository) -> None:
        self.repo = repo
        self.settings = get_settings()
        instructions = Path("app/prompts/quiz.md").read_text()
        self.agent = Agent(
            name="QuizAgent",
            instructions=instructions,
            tools=[search_docs],
            model=self.settings.openai_model,
            output_type=QuizQuestion,
        )

    async def generate(self, topic_id: str) -> QuizQuestion:
        if not self.settings.openai_api_key:
            return QuizQuestion(
                topic_id="processing.dataflow.windowing",
                question=(
                    "A streaming pipeline receives out-of-order events and must report hourly "
                    "aggregates with corrections for late data. Which design choice is most important?"
                    "(Note that this is the only available question as the API key is not set.)"
                ),
                choices=[
                    "Use event-time windowing with allowed lateness and triggers.",
                    "Use processing-time windows only.",
                    "Load events directly into a clustered BigQuery table.",
                    "Disable acknowledgements in Pub/Sub.",
                ],
                correct_answer="Use event-time windowing with allowed lateness and triggers.",
                explanation=(
                    "Event-time windowing models when events occurred. Allowed lateness and triggers "
                    "balance early output with late corrections."
                ),
            )
        prompt = (
            "Generate one multiple-choice question as JSON with keys: topic_id, question, "
            "choices, correct_answer, explanation. choices must be a JSON array of strings. "
            "correct_answer must exactly match one item in choices. "
            f"Target topic: {topic_id}."
        )
        with trace(
            "steady-current-quiz",
            group_id="quiz-generation",
            metadata={"topic_id": topic_id},
        ):
            result = await Runner.run(self.agent, prompt)
        flush_traces()
        return _parse_quiz_output(result.final_output, topic_id)
