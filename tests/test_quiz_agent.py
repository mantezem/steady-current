from __future__ import annotations

from app.agents.quiz import _parse_quiz_output


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
