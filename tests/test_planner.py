from __future__ import annotations

import pytest

from app.models.schemas import MasteryRecord, RelationshipType, Topic, TopicRelationship
from app.planner.service import StudyPlanner


class FakePlannerRepo:
    def __init__(
        self,
        topics: list[Topic],
        mastery: list[MasteryRecord],
        relationships: list[TopicRelationship],
    ) -> None:
        self._topics = topics
        self._mastery = mastery
        self._relationships = relationships

    async def list_topics(self) -> list[Topic]:
        return self._topics

    async def list_mastery(self, user_id: str) -> list[MasteryRecord]:
        return self._mastery

    async def list_relationships(
        self,
        relationship_type: RelationshipType | None = None,
    ) -> list[TopicRelationship]:
        if relationship_type is None:
            return self._relationships
        return [item for item in self._relationships if item.relationship_type == relationship_type]


@pytest.mark.asyncio
async def test_recommend_topic_prioritizes_low_confidence_before_lower_mastery() -> None:
    repo = FakePlannerRepo(
        topics=[
            Topic(id="data_engineering", title="Foundations", domain="foundation", sort_order=1),
            Topic(id="topic.a", title="Topic A", domain="analytics", sort_order=10),
            Topic(id="topic.b", title="Topic B", domain="analytics", sort_order=11),
        ],
        mastery=[
            MasteryRecord(topic_id="data_engineering", title="Foundations", mastery=1.0, confidence=1.0),
            MasteryRecord(topic_id="topic.a", title="Topic A", mastery=0.5, confidence=0.2, attempts=2),
            MasteryRecord(topic_id="topic.b", title="Topic B", mastery=0.1, confidence=0.8, attempts=0),
        ],
        relationships=[
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
        ],
    )

    recommendation = await StudyPlanner(repo).recommend_topic("default-user", 30)

    assert recommendation is not None
    assert recommendation.topic_id == "topic.a"
    assert recommendation.reason == "Reinforce low-confidence topic"


@pytest.mark.asyncio
async def test_recommend_topic_excludes_blocked_topics() -> None:
    repo = FakePlannerRepo(
        topics=[
            Topic(id="data_engineering", title="Foundations", domain="foundation", sort_order=1),
            Topic(id="topic.a", title="Topic A", domain="analytics", sort_order=10),
            Topic(id="topic.b", title="Topic B", domain="analytics", sort_order=11),
        ],
        mastery=[
            MasteryRecord(topic_id="data_engineering", title="Foundations", mastery=0.4, confidence=0.4),
            MasteryRecord(topic_id="topic.a", title="Topic A", mastery=0.2, confidence=0.2),
            MasteryRecord(topic_id="topic.b", title="Topic B", mastery=0.1, confidence=0.1),
        ],
        relationships=[
            TopicRelationship(
                source_topic_id="data_engineering",
                target_topic_id="topic.a",
                relationship_type=RelationshipType.prerequisite,
            ),
            TopicRelationship(
                source_topic_id="topic.a",
                target_topic_id="topic.b",
                relationship_type=RelationshipType.prerequisite,
            ),
        ],
    )

    recommendation = await StudyPlanner(repo).recommend_topic("default-user", 30)

    assert recommendation is None
