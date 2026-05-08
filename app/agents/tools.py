from __future__ import annotations

from agents import function_tool

from app.db.connection import get_pool
from app.db.repositories import LearningRepository
from app.retrieval.service import RetrievalService


@function_tool
async def search_docs(query: str, topic_id: str | None = None, top_k: int = 5) -> str:
    """Search the learning resource corpus and return cited context."""
    pool = await get_pool()
    repo = LearningRepository(pool)
    retrieval = RetrievalService(repo)
    chunks = await retrieval.search(query=query, topic_id=topic_id, top_k=top_k)
    return retrieval.format_citations(chunks)
