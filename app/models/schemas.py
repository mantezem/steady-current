from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class RelationshipType(StrEnum):
    parent = "parent"
    prerequisite = "prerequisite"
    related = "related"


class Topic(BaseModel):
    id: str
    title: str
    domain: str
    description: str = ""
    depth: int = 0
    sort_order: int = 0


class TopicRelationship(BaseModel):
    source_topic_id: str
    target_topic_id: str
    relationship_type: RelationshipType


class MasteryRecord(BaseModel):
    topic_id: str
    title: str = ""
    mastery: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    attempts: int = 0
    correct_attempts: int = 0
    last_reviewed_at: datetime | None = None


class Resource(BaseModel):
    url: HttpUrl
    title: str
    service: str = ""
    source_type: str
    updated_at: datetime | None = None


class DocumentChunk(BaseModel):
    content: str
    topic_id: str | None = None
    service: str = ""
    source_url: str
    source_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class RetrievedChunk(DocumentChunk):
    id: int
    title: str
    similarity: float


class StudySetup(BaseModel):
    study_timeline: str
    preferences: str = ""
    strengths: str = ""
    weaknesses: str = ""


class StudyPlanItem(BaseModel):
    topic_id: str
    title: str
    reason: str
    estimated_minutes: int
    mastery: float


class QuizQuestion(BaseModel):
    topic_id: str
    question: str
    choices: list[str]
    correct_answer: str
    explanation: str


class EvaluationResult(BaseModel):
    is_correct: bool
    explanation: str
    mastery: float
    confidence: float
