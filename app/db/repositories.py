from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

import asyncpg

from app.models.schemas import (
    DocumentChunk,
    MasteryRecord,
    RelationshipType,
    Resource,
    RetrievedChunk,
    Topic,
    TopicRelationship,
)


def _vector_literal(embedding: list[float] | None) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


def _jsonb(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


class LearningRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def upsert_topic(self, topic: Topic) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO topics (id, title, domain, description, depth, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    domain = EXCLUDED.domain,
                    description = EXCLUDED.description,
                    depth = EXCLUDED.depth,
                    sort_order = EXCLUDED.sort_order
                """,
                topic.id,
                topic.title,
                topic.domain,
                topic.description,
                topic.depth,
                topic.sort_order,
            )

    async def upsert_relationship(self, relationship: TopicRelationship) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO topic_relationships
                    (source_topic_id, target_topic_id, relationship_type)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                relationship.source_topic_id,
                relationship.target_topic_id,
                relationship.relationship_type.value,
            )

    async def list_topics(self) -> list[Topic]:
        rows = await self.pool.fetch("SELECT * FROM topics ORDER BY domain, depth, sort_order, id")
        return [Topic(**dict(row)) for row in rows]

    async def list_relationships(
        self, relationship_type: RelationshipType | None = None
    ) -> list[TopicRelationship]:
        if relationship_type is None:
            rows = await self.pool.fetch("SELECT * FROM topic_relationships")
        else:
            rows = await self.pool.fetch(
                "SELECT * FROM topic_relationships WHERE relationship_type = $1",
                relationship_type.value,
            )
        return [
            TopicRelationship(
                source_topic_id=row["source_topic_id"],
                target_topic_id=row["target_topic_id"],
                relationship_type=RelationshipType(row["relationship_type"]),
            )
            for row in rows
        ]

    async def list_mastery(self, user_id: str) -> list[MasteryRecord]:
        rows = await self.pool.fetch(
            """
            SELECT t.id AS topic_id, t.title, COALESCE(m.mastery, 0) AS mastery,
                   COALESCE(m.confidence, 0) AS confidence,
                   COALESCE(m.attempts, 0) AS attempts,
                   COALESCE(m.correct_attempts, 0) AS correct_attempts,
                   m.last_reviewed_at
            FROM topics t
            LEFT JOIN user_mastery m ON m.topic_id = t.id AND m.user_id = $1
            ORDER BY t.domain, t.depth, t.sort_order, t.id
            """,
            user_id,
        )
        return [MasteryRecord(**dict(row)) for row in rows]

    async def record_attempt(
        self,
        user_id: str,
        topic_id: str,
        question: str,
        answer: str,
        correct_answer: str,
        is_correct: bool,
        explanation: str,
    ) -> MasteryRecord:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO question_attempts
                        (user_id, topic_id, question, answer, correct_answer, is_correct, explanation)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    user_id,
                    topic_id,
                    question,
                    answer,
                    correct_answer,
                    is_correct,
                    explanation,
                )
                await conn.execute(
                    """
                    INSERT INTO user_mastery
                        (user_id, topic_id, mastery, confidence, attempts, correct_attempts, last_reviewed_at)
                    VALUES ($1, $2, $3, $4, 1, $5, now())
                    ON CONFLICT (user_id, topic_id) DO UPDATE SET
                        attempts = user_mastery.attempts + 1,
                        correct_attempts = user_mastery.correct_attempts + $5,
                        mastery = (user_mastery.correct_attempts + $5)::float
                                  / NULLIF(user_mastery.attempts + 1, 0),
                        confidence = LEAST(1.0, (user_mastery.attempts + 1)::float / 10.0),
                        last_reviewed_at = now()
                    """,
                    user_id,
                    topic_id,
                    1.0 if is_correct else 0.0,
                    0.1,
                    1 if is_correct else 0,
                )
                row = await conn.fetchrow(
                    """
                    SELECT m.topic_id, t.title, m.mastery, m.confidence, m.attempts,
                           m.correct_attempts, m.last_reviewed_at
                    FROM user_mastery m
                    JOIN topics t ON t.id = m.topic_id
                    WHERE m.user_id = $1 AND m.topic_id = $2
                    """,
                    user_id,
                    topic_id,
                )
        if row is None:
            raise RuntimeError("Failed to update mastery")
        return MasteryRecord(**dict(row))

    async def upsert_resource(self, resource: Resource) -> int:
        row = await self.pool.fetchrow(
            """
            INSERT INTO resources (url, title, service, source_type, updated_at)
            VALUES ($1, $2, $3, $4, COALESCE($5, now()))
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                service = EXCLUDED.service,
                source_type = EXCLUDED.source_type,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            str(resource.url),
            resource.title,
            resource.service,
            resource.source_type,
            resource.updated_at,
        )
        return int(row["id"])

    async def upsert_chunk(
        self, resource_id: int, chunk: DocumentChunk, embedding: list[float] | None
    ) -> None:
        content_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
        await self.pool.execute(
            """
            INSERT INTO document_chunks
                (resource_id, topic_id, content, service, source_url, source_type,
                metadata, embedding, updated_at, content_hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::vector, COALESCE($9, now()), $10)
            ON CONFLICT (resource_id, content_hash) DO UPDATE SET
                topic_id = EXCLUDED.topic_id,
                content = EXCLUDED.content,
                service = EXCLUDED.service,
                source_url = EXCLUDED.source_url,
                source_type = EXCLUDED.source_type,
                metadata = EXCLUDED.metadata,
                embedding = COALESCE(EXCLUDED.embedding, document_chunks.embedding),
                updated_at = EXCLUDED.updated_at
            """,
            resource_id,
            chunk.topic_id,
            chunk.content,
            chunk.service,
            chunk.source_url,
            chunk.source_type,
            json.dumps(chunk.metadata),
            _vector_literal(embedding),
            chunk.updated_at,
            content_hash,
        )

    async def count_chunks(self) -> int:
        return int(await self.pool.fetchval("SELECT COUNT(*) FROM document_chunks"))

    async def count_chunks_missing_embeddings(self, source_urls: list[str] | None = None) -> int:
        if source_urls is None:
            return int(
                await self.pool.fetchval(
                    "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NULL"
                )
            )
        return int(
            await self.pool.fetchval(
                """
                SELECT COUNT(*)
                FROM document_chunks c
                JOIN resources r ON r.id = c.resource_id
                WHERE c.embedding IS NULL AND r.url = ANY($1::text[])
                """,
                source_urls,
            )
        )

    async def search_chunks(
        self,
        embedding: list[float] | None,
        query: str,
        topic_id: str | None,
        metadata_filter: dict[str, Any] | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        clauses = []
        values: list[Any] = []
        if topic_id:
            values.append(topic_id)
            clauses.append(f"c.topic_id = ${len(values)}")
        if metadata_filter:
            values.append(json.dumps(metadata_filter))
            clauses.append(f"c.metadata @> ${len(values)}::jsonb")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        if embedding is not None:
            clauses.append("c.embedding IS NOT NULL")
            where = f"WHERE {' AND '.join(clauses)}"
            values.extend([_vector_literal(embedding), top_k])
            vector_param = len(values) - 1
            limit_param = len(values)
            sql = f"""
                SELECT c.*, r.title, 1 - (c.embedding <=> ${vector_param}) AS similarity
                FROM document_chunks c
                JOIN resources r ON r.id = c.resource_id
                {where}
                ORDER BY c.embedding <=> ${vector_param}::vector
                LIMIT ${limit_param}
            """
        else:
            values.extend([query, top_k])
            query_param = len(values) - 1
            limit_param = len(values)
            sql = f"""
                SELECT c.*, r.title,
                       ts_rank_cd(to_tsvector('english', c.content), plainto_tsquery('english', ${query_param}))
                       AS similarity
                FROM document_chunks c
                JOIN resources r ON r.id = c.resource_id
                {where}
                ORDER BY similarity DESC, c.updated_at DESC
                LIMIT ${limit_param}
            """
        rows = await self.pool.fetch(sql, *values)
        return [
            RetrievedChunk(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                topic_id=row["topic_id"],
                service=row["service"],
                source_url=row["source_url"],
                source_type=row["source_type"],
                metadata=_jsonb(row["metadata"]),
                updated_at=row["updated_at"],
                similarity=float(row["similarity"] or 0),
            )
            for row in rows
        ]

    async def topic_tree_markdown(self, user_id: str) -> str:
        topics = {topic.id: topic for topic in await self.list_topics()}
        mastery = {item.topic_id: item for item in await self.list_mastery(user_id)}
        parents = defaultdict(list)
        for rel in await self.list_relationships(RelationshipType.parent):
            parents[rel.source_topic_id].append(rel.target_topic_id)
        child_ids = {child for children in parents.values() for child in children}
        roots = [topic_id for topic_id in topics if topic_id not in child_ids]

        def render(topic_id: str, depth: int = 0) -> list[str]:
            topic = topics[topic_id]
            record = mastery.get(topic_id)
            pct = int((record.mastery if record else 0) * 100)
            lines = [f"{'  ' * depth}- {topic.title} ({pct}%)"]
            for child_id in sorted(parents[topic_id], key=lambda item: topics[item].sort_order):
                lines.extend(render(child_id, depth + 1))
            return lines

        output: list[str] = []
        for root in sorted(roots, key=lambda item: (topics[item].domain, topics[item].sort_order)):
            output.extend(render(root))
        return "\n".join(output)
