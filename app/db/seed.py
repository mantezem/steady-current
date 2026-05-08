from __future__ import annotations

from pathlib import Path

import asyncpg
import yaml

from app.db.repositories import LearningRepository
from app.ingestion.pipeline import ingest_seed_resources, seed_resource_urls
from app.models.schemas import Resource, Topic, TopicRelationship
from app.utils.config import get_settings


def _load_seed_section(filename: str, section: str) -> list[dict]:
    path = Path(__file__).with_name(filename)
    data = yaml.safe_load(path.read_text()) or {}
    return data.get(section, [])


async def seed_initial_data(pool: asyncpg.Pool) -> None:
    repo = LearningRepository(pool)
    for item in _load_seed_section("topics.yaml", "topics"):
        await repo.upsert_topic(Topic(**item))
    for item in _load_seed_section("relationships.yaml", "relationships"):
        await repo.upsert_relationship(TopicRelationship(**item))
    for item in _load_seed_section("resources.yaml", "resources"):
        await repo.upsert_resource(Resource(**item))
    if await repo.count_chunks() == 0:
        await ingest_seed_resources(repo)
    elif get_settings().openai_api_key and await repo.count_chunks_missing_embeddings(
        seed_resource_urls()
    ):
        await ingest_seed_resources(repo)
