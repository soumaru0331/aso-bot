import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "bot.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        with open("models/schema.sql") as f:
            await db.executescript(f.read())
        await db.commit()
