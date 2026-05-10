import asyncio
import traceback
import discord
from discord.ext import commands
from config import TOKEN
from database import init_db, get_pool
from scheduler import start_scheduler
from keep_alive import start_web_server


class AsoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("[AsoBot] setup_hook 開始")
        await init_db()
        print("[AsoBot] DB初期化完了")

        from cogs.recruit import RecruitView
        pool = await get_pool()
        rows = await pool.fetch("SELECT id FROM recruitments WHERE status = 'open'")
        for record in rows:
            self.add_view(RecruitView(record["id"]))
        print(f"[AsoBot] Persistent View {len(rows)}件再登録完了")

        await self.load_extension("cogs.recruit")
        print("[AsoBot] cogs.recruit 読み込み完了")
        await self.load_extension("cogs.notifications")
        print("[AsoBot] cogs.notifications 読み込み完了")
        await self.tree.sync()
        print("[AsoBot] スラッシュコマンド同期完了")
        start_scheduler(self)
        print("[AsoBot] スケジューラ起動完了")

    async def on_ready(self):
        print(f"[AsoBot] {self.user} としてログインしました")
        print(f"[AsoBot] {len(self.guilds)} サーバーに接続中")


async def main():
    start_web_server()
    bot = AsoBot()
    try:
        async with bot:
            await bot.start(TOKEN)
    except Exception:
        print("[AsoBot] 起動エラー:")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
