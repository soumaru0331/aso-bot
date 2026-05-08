import asyncio
import discord
from discord.ext import commands
import aiosqlite

from config import TOKEN
from database import init_db, DB_PATH
from scheduler import start_scheduler


class AsoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()

        # Persistent ViewをBot再起動後も有効化するため全open募集を再登録
        from cogs.recruit import RecruitView
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id FROM recruitments WHERE status = 'open'"
            ) as cursor:
                rows = await cursor.fetchall()
        for (recruitment_id,) in rows:
            self.add_view(RecruitView(recruitment_id))

        await self.load_extension("cogs.recruit")
        await self.load_extension("cogs.notifications")
        await self.tree.sync()
        start_scheduler(self)

    async def on_ready(self):
        print(f"[AsoBot] {self.user} としてログインしました")
        print(f"[AsoBot] {len(self.guilds)} サーバーに接続中")


async def main():
    bot = AsoBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
