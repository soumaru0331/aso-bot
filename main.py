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
        while True:
            try:
                await init_db()
                break
            except Exception as e:
                print(f"[AsoBot] DB接続失敗（60秒後に再試行）: {e}", flush=True)
                await asyncio.sleep(60)
        print("[AsoBot] DB初期化完了")

        pool = await get_pool()

        from cogs.recruit import RecruitView
        rows = await pool.fetch("SELECT id FROM recruitments WHERE status = 'open'")
        for record in rows:
            self.add_view(RecruitView(record["id"]))
        print(f"[AsoBot] Persistent View {len(rows)}件再登録完了")

        for ext in ("cogs.recruit", "cogs.notifications", "cogs.panel"):
            try:
                await self.load_extension(ext)
                print(f"[AsoBot] {ext} 読み込み完了")
            except Exception as e:
                print(f"[AsoBot] {ext} 読み込み失敗: {e}", flush=True)
                import traceback; traceback.print_exc()

        from cogs.panel import RulesView, RolePanelView
        panels = await pool.fetch("SELECT id, panel_type FROM role_panels")
        for p in panels:
            buttons = await pool.fetch(
                "SELECT role_id, label FROM role_panel_buttons WHERE panel_id = $1", p["id"]
            )
            if p["panel_type"] == "rules" and buttons:
                self.add_view(RulesView(p["id"], int(buttons[0]["role_id"])))
            elif p["panel_type"] == "role":
                self.add_view(RolePanelView(p["id"], [dict(b) for b in buttons]))
        print(f"[AsoBot] パネルView {len(panels)}件再登録完了")

        start_scheduler(self)
        print("[AsoBot] スケジューラ起動完了")

    async def on_ready(self):
        print(f"[AsoBot] {self.user} としてログインしました")
        print(f"[AsoBot] {len(self.guilds)} サーバーに接続中")
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"[AsoBot] {guild.name}: {len(synced)}コマンド同期完了")
            except Exception as e:
                print(f"[AsoBot] {guild.name}: 同期失敗 {e}")


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
