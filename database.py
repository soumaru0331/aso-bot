from __future__ import annotations
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
DB_PATH = os.getenv("DB_PATH", "bot.db")  # テスト用SQLite互換パス

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


async def init_db() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        with open("models/schema.sql") as f:
            await conn.execute(f.read())
