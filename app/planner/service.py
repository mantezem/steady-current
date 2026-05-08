from __future__ import annotations

from collections import defaultdict

from app.db.repositories import LearningRepository
from app.models.schemas import RelationshipType, StudyPlanItem


class StudyPlanner:
    def __init__(self, repo: LearningRepository) -> None:
        self.repo = repo

    async def plan(self, user_id: str, available_minutes: int) -> list[StudyPlanItem]:
        topics = {topic.id: topic for topic in await self.repo.list_topics()}
        mastery = {record.topic_id: record for record in await self.repo.list_mastery(user_id)}
        prerequisites: dict[str, set[str]] = defaultdict(set)
        for rel in await self.repo.list_relationships(RelationshipType.prerequisite):
            prerequisites[rel.target_topic_id].add(rel.source_topic_id)

        eligible: list[StudyPlanItem] = []
        for topic_id, topic in topics.items():
            if topic_id == "data_engineering":
                continue
            blocked_by = [
                prereq
                for prereq in prerequisites.get(topic_id, set())
                if mastery.get(prereq, None) is None or mastery[prereq].mastery < 0.55
            ]
            record = mastery[topic_id]
            if blocked_by:
                continue
            if record.mastery < 0.7:
                reason = (
                    "Reinforce weak area"
                    if record.attempts > 0
                    else "New topic unlocked by prerequisites"
                )
                eligible.append(
                    StudyPlanItem(
                        topic_id=topic_id,
                        title=topic.title,
                        reason=reason,
                        estimated_minutes=20,
                        mastery=record.mastery,
                    )
                )

        eligible.sort(key=lambda item: (item.mastery, topics[item.topic_id].sort_order))
        count = max(1, available_minutes // 20)
        return eligible[:count]
