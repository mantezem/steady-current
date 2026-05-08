from __future__ import annotations

import asyncio

import asyncpg

from app.utils.config import get_settings

_pool: asyncpg.Pool | None = None
_pool_loop: object | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool, _pool_loop
    running_loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop is not running_loop:
        if _pool is not None:
            await _pool.close()
        settings = get_settings()
        _pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=5)
        _pool_loop = running_loop
    return _pool


async def close_pool() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        await _pool.close()
        _pool = None
        _pool_loop = None
