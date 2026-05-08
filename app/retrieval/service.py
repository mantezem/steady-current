from __future__ import annotations

from typing import Any

from app.db.repositories import LearningRepository
from app.models.schemas import RetrievedChunk
from app.retrieval.embeddings import EmbeddingService
from app.utils.config import get_settings


class RetrievalService:
    def __init__(self, repo: LearningRepository, embeddings: EmbeddingService | None = None) -> None:
        self.repo = repo
        self.embeddings = embeddings or EmbeddingService()
        self.settings = get_settings()

    async def search(
        self,
        query: str,
        topic_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        embedding = await self.embeddings.embed(query)
        return await self.repo.search_chunks(
            embedding=embedding,
            query=query,
            topic_id=topic_id,
            metadata_filter=metadata_filter,
            top_k=top_k or self.settings.retrieval_top_k,
        )

    @staticmethod
    def format_citations(chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "No matching sources were found."
        lines = []
        for index, chunk in enumerate(chunks, start=1):
            lines.append(
                f"[{index}] {chunk.title} ({chunk.source_type}) - {chunk.source_url}\n"
                f"{chunk.content[:700]}"
            )
        return "\n\n".join(lines)
