from __future__ import annotations

from app.models.schemas import RetrievedChunk
from app.retrieval.service import RetrievalService


def test_format_citations_renders_clickable_markdown_links() -> None:
    citations = RetrievalService.format_citations(
        [
            RetrievedChunk(
                id=1,
                title="Streaming Pipelines",
                source_type="doc",
                source_url="https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines",
                content="Use event-time semantics for late data handling.",
                topic_id="processing.dataflow.windowing",
                service="dataflow",
                metadata={},
                updated_at=None,
                similarity=0.9,
            )
        ]
    )

    assert (
        "[1] [Streaming Pipelines (doc)]"
        "(https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines)"
    ) in citations
