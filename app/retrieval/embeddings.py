from __future__ import annotations

from openai import AsyncOpenAI

from app.utils.config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = (
            AsyncOpenAI(api_key=self.settings.openai_api_key)
            if self.settings.openai_api_key
            else None
        )

    async def embed(self, text: str) -> list[float] | None:
        if self.client is None:
            return None
        response = await self.client.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=text,
            dimensions=self.settings.openai_embedding_dimensions,
        )
        return response.data[0].embedding
