from __future__ import annotations

import asyncio
from typing import NamedTuple

from app.db.connection import close_pool, get_pool
from app.db.migrate import migrate
from app.db.repositories import LearningRepository
from app.models.schemas import DocumentChunk, Resource
from app.retrieval.chunking import semantic_chunks
from app.retrieval.embeddings import EmbeddingService


class SeedDocument(NamedTuple):
    resource: Resource
    topic_id: str
    body: str


SEED_DOCUMENTS = [
    SeedDocument(
        Resource(
            url="https://cloud.google.com/bigquery/docs/partitioned-tables",
            title="Introduction to partitioned tables",
            service="BigQuery",
            source_type="official_docs",
        ),
        "storage.bigquery.partitioning",
        """
        BigQuery partitioned tables divide data into segments that can be scanned selectively.
        Partitioning is commonly based on ingestion time, time-unit columns, or integer ranges.
        For certification scenarios, partitioning is usually the first cost-control and performance
        choice when queries filter by date or a bounded range. It reduces bytes scanned and makes
        retention policies easier to manage.

        Tradeoffs:
        Partitioning only helps when queries include filters on the partitioning column. Too many
        tiny partitions can add metadata overhead. For high-cardinality dimensions that are not good
        partition keys, combine partitioning with clustering.
        """,
    ),
    SeedDocument(
        Resource(
            url="https://cloud.google.com/bigquery/docs/clustered-tables",
            title="Introduction to clustered tables",
            service="BigQuery",
            source_type="official_docs",
        ),
        "storage.bigquery.clustering",
        """
        BigQuery clustered tables organize storage blocks by selected columns. Clustering improves
        pruning when queries filter or aggregate by those columns, especially after partitioning has
        already narrowed the scan. Choose clustering columns based on frequent filters, joins, and
        group-by patterns.

        Tradeoffs:
        Clustering is adaptive and does not guarantee exact block layout. It is best for repeated
        access patterns and can reduce cost, but it should not replace partitioning when time-based
        pruning or lifecycle management is required.
        """,
    ),
    SeedDocument(
        Resource(
            url="https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines",
            title="Streaming pipelines",
            service="Dataflow",
            source_type="official_docs",
        ),
        "processing.dataflow.windowing",
        """
        Dataflow uses Apache Beam concepts for event-time processing. Windowing groups unbounded
        events into finite panes so aggregations can produce meaningful results. Fixed windows,
        sliding windows, and sessions model different business questions.

        Operational reasoning:
        Use event time when late or out-of-order events matter. Use triggers and allowed lateness
        when the business needs early results and later corrections. Windowing choices affect
        correctness, latency, state size, and cost.
        """,
    ),
    SeedDocument(
        Resource(
            url="https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines",
            title="Streaming pipelines",
            service="Dataflow",
            source_type="official_docs",
        ),
        "processing.dataflow.watermarks",
        """
        Watermarks estimate how complete event-time data is for a given point in time. They help
        Dataflow decide when to emit windowed results. Late data can still arrive after the
        watermark, so pipelines must define allowed lateness and accumulation behavior.

        Certification scenarios often test whether a pipeline should optimize for low latency,
        final correctness, or bounded state. Watermarks are not perfect clocks; they are progress
        signals derived from source behavior.
        """,
    ),
    SeedDocument(
        Resource(
            url="https://cloud.google.com/pubsub/docs/overview",
            title="Pub/Sub overview",
            service="Pub/Sub",
            source_type="official_docs",
        ),
        "messaging.pubsub",
        """
        Pub/Sub is a global messaging service for decoupling producers and consumers. It supports
        push and pull subscriptions, ack deadlines, retention, replay by seeking, and ordering keys
        for scoped ordering. It is commonly paired with Dataflow for streaming ingestion.

        Tradeoffs:
        Pub/Sub provides at-least-once delivery, so downstream systems must handle duplicates.
        Ordering keys can constrain parallelism. Choose Pub/Sub when ingestion needs durable,
        scalable decoupling rather than direct service-to-service calls.
        """,
    ),
]


def seed_resource_urls() -> list[str]:
    return [str(document.resource.url) for document in SEED_DOCUMENTS]


async def ingest_seed_resources(repo: LearningRepository) -> None:
    embeddings = EmbeddingService()
    for document in SEED_DOCUMENTS:
        resource_id = await repo.upsert_resource(document.resource)
        for content in semantic_chunks(document.body):
            chunk = DocumentChunk(
                content=content,
                topic_id=document.topic_id,
                service=document.resource.service,
                source_url=str(document.resource.url),
                source_type=document.resource.source_type,
                metadata={
                    "service": document.resource.service,
                    "topic": document.topic_id,
                    "source_url": str(document.resource.url),
                    "source_type": document.resource.source_type,
                },
            )
            await repo.upsert_chunk(resource_id, chunk, await embeddings.embed(content))


async def main() -> None:
    pool = await get_pool()
    await migrate(pool)
    repo = LearningRepository(pool)
    await ingest_seed_resources(repo)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
