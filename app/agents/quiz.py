from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agents import Agent, Runner, flush_traces, trace

from app.agents.tools import search_docs
from app.db.repositories import LearningRepository
from app.models.schemas import MasteryRecord, QuizQuestion, Topic
from app.utils.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_quiz_payload(data: dict[str, Any], topic_id: str) -> dict[str, Any]:
    data["topic_id"] = topic_id

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


def _target_difficulty(topic: Topic | None, mastery: MasteryRecord | None) -> str:
    base = (topic.difficulty if topic is not None else "intermediate").lower()
    if mastery is not None and (mastery.mastery >= 0.7 or mastery.confidence >= 0.7):
        return "advanced"
    if base == "beginner":
        return "intermediate"
    if base == "intermediate":
        return "advanced"
    return "advanced"


def _build_quiz_prompt(
    topic_id: str,
    topic: Topic | None,
    mastery: MasteryRecord | None,
) -> str:
    topic_title = topic.title if topic is not None else topic_id
    topic_description = topic.description if topic is not None else "No description available."
    topic_difficulty = topic.difficulty if topic is not None else "intermediate"
    target_difficulty = _target_difficulty(topic, mastery)
    mastery_summary = (
        f"mastery={mastery.mastery:.0%}, confidence={mastery.confidence:.0%}, attempts={mastery.attempts}"
        if mastery is not None
        else "no prior mastery data"
    )
    return (
        "Generate exactly one certification-style multiple-choice question as JSON with keys: "
        "topic_id, question, choices, correct_answer, explanation. "
        "choices must be a JSON array of strings. correct_answer must exactly match one item in choices.\n"
        f"Target topic ID: {topic_id}\n"
        f"Target topic title: {topic_title}\n"
        f"Topic description: {topic_description}\n"
        f"Topic catalog difficulty: {topic_difficulty}\n"
        f"Learner calibration: {mastery_summary}\n"
        f"Required question difficulty: {target_difficulty}\n"
        "Write a scenario-based question that requires architecture judgment, troubleshooting, operational tradeoffs, "
        "or failure analysis. Do not ask for a term definition, a single feature recall, or an obvious best practice.\n"
        "Use plausible distractors that would look credible to a partially prepared learner. "
        "At least two wrong answers should fail for subtle but concrete reasons.\n"
        "The explanation must justify the correct answer and briefly explain why each distractor is wrong.\n"
        "Prefer constraints involving latency, correctness, cost, governance, scale, or late/failing data."
    )


def _fallback_quiz_question(topic_id: str, topic: Topic | None) -> QuizQuestion:
    prompt_topic = topic.title if topic is not None else topic_id
    topic_key = topic_id.lower()
    if "bigquery" in topic_key:
        return QuizQuestion(
            topic_id=topic_id,
            question=(
                f"A team uses {prompt_topic} for daily reporting. Queries still scan too much data even after "
                "partitioning by `event_date`, and analysts frequently filter by `customer_id` and narrow date ranges. "
                "Which change is most likely to reduce scan cost without breaking existing SQL?"
            ),
            choices=[
                "Cluster the partitioned table by `customer_id` and keep partition filters in queries.",
                "Convert the table to processing-time partitions and stop filtering on `event_date`.",
                "Move the data to Cloud SQL so customer filters can use B-tree indexes.",
                "Create one table per customer and use wildcard queries across all customers.",
            ],
            correct_answer="Cluster the partitioned table by `customer_id` and keep partition filters in queries.",
            explanation=(
                "Clustering complements partition pruning by organizing data within each partition around the fields "
                "most often filtered. Processing-time partitions weaken business-date pruning, Cloud SQL is the wrong "
                "analytics engine at this scale, and per-customer sharding increases management overhead and query complexity."
            ),
        )
    if "dataflow" in topic_key or "window" in topic_key or "stream" in topic_key:
        return QuizQuestion(
            topic_id=topic_id,
            question=(
                "A streaming pipeline must publish hourly revenue totals within five minutes of the hour, but finance "
                "also needs late mobile events folded into the final totals when they arrive up to two hours late. "
                "Which design is most appropriate?"
            ),
            choices=[
                "Use event-time fixed windows with an early trigger, allowed lateness, and accumulating panes.",
                "Use processing-time windows so results always emit on wall-clock boundaries and ignore event timestamps.",
                "Write each event directly to BigQuery and recompute the entire day every five minutes.",
                "Buffer events in Pub/Sub for two hours before processing so all data arrives on time.",
            ],
            correct_answer="Use event-time fixed windows with an early trigger, allowed lateness, and accumulating panes.",
            explanation=(
                "This approach balances low-latency preliminary results with correctness for late data. "
                "Processing-time windows lose event-time semantics, full recomputation is costly and unnecessary, "
                "and delaying all processing violates the five-minute reporting requirement."
            ),
        )
    return QuizQuestion(
        topic_id=topic_id,
        question=(
            f"You are reviewing a production design for {prompt_topic}. Two options both satisfy the happy path, "
            "but one degrades badly under scale, cost pressure, and operational failures. What should the learner focus on first?"
        ),
        choices=[
            "Choose the design that preserves correctness and operability under stated constraints, even if it is less simple.",
            "Choose the option with the fewest managed services because fewer services are always easier to run.",
            "Choose the lowest-cost option on day one, even if it increases recovery time and manual work later.",
            "Choose the option that stores the most raw data, because more data automatically means better architecture.",
        ],
        correct_answer="Choose the design that preserves correctness and operability under stated constraints, even if it is less simple.",
        explanation=(
            "Certification-style architecture questions usually turn on explicit constraints such as correctness, recovery, "
            "scale, governance, or latency. Simplicity and raw cost matter, but not when they trade away the required behavior."
        ),
    )


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
        topic = await self.repo.get_topic(topic_id)
        mastery = next(
            (
                record
                for record in await self.repo.list_mastery(self.settings.app_user_id)
                if record.topic_id == topic_id
            ),
            None,
        )
        if not self.settings.openai_api_key:
            logger.info("OpenAI API key not found; providing default quiz question for topic_id=%s", topic_id)
            return _fallback_quiz_question(topic_id, topic)
        logger.info("OpenAI API key found; generating quiz question for topic_id=%s", topic_id)
        prompt = _build_quiz_prompt(topic_id, topic, mastery)
        with trace(
            "steady-current-quiz",
            group_id="quiz-generation",
            metadata={"topic_id": topic_id},
        ):
            result = await Runner.run(self.agent, prompt)
        flush_traces()
        return _parse_quiz_output(result.final_output, topic_id)
