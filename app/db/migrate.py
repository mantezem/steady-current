from __future__ import annotations

import re
from pathlib import Path

import asyncpg

from app.utils.config import get_settings


async def _ensure_embedding_dimensions(conn: asyncpg.Connection, dimensions: int) -> None:
    current_type = await conn.fetchval(
        """
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'document_chunks'
          AND a.attname = 'embedding'
          AND NOT a.attisdropped
        """
    )
    match = re.fullmatch(r"vector\((\d+)\)", current_type or "")
    if match is not None and int(match.group(1)) == dimensions:
        return

    await conn.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding")
    await conn.execute(
        f"""
        ALTER TABLE document_chunks
        ALTER COLUMN embedding TYPE vector({dimensions})
        USING NULL
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
        ON document_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


async def migrate(pool: asyncpg.Pool) -> None:
    settings = get_settings()
    schema = Path(__file__).with_name("schema.sql").read_text().replace(
        "{embedding_dimensions}", str(settings.openai_embedding_dimensions)
    )
    async with pool.acquire() as conn:
        await conn.execute(schema)
        await _ensure_embedding_dimensions(conn, settings.openai_embedding_dimensions)
