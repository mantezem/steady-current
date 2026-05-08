from __future__ import annotations

import asyncio

from app.db.connection import close_pool, get_pool
from app.db.migrate import migrate
from app.db.seed import seed_initial_data
from app.ui.app import build_ui
from app.utils.config import get_settings


async def bootstrap() -> None:
    pool = await get_pool()
    await migrate(pool)
    await seed_initial_data(pool)
    await close_pool()


def main() -> None:
    settings = get_settings()
    asyncio.run(bootstrap())
    ui = build_ui()
    ui.launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
    )


if __name__ == "__main__":
    main()
