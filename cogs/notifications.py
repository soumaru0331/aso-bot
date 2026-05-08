from __future__ import annotations
import discord
from discord.ext import commands
import aiosqlite
from database import DB_PATH


async def send_dm_notification(bot: discord.Client, recruitment_id: int, minutes_before: int) -> None:
    """参加者に開始X分前DM通知を送る。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM recruitments WHERE id = ?", (recruitment_id,)
        ) as cursor:
            recruitment = await cursor.fetchone()
        if not recruitment or recruitment["status"] != "open":
            return

        async with db.execute(
            "SELECT user_id FROM participants "
            "WHERE recruitment_id = ? AND join_type IN ('confirmed','late','partial')",
            (recruitment_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        await db.execute(
            "UPDATE notifications SET sent = 1 "
            "WHERE recruitment_id = ? AND minutes_before = ?",
            (recruitment_id, minutes_before),
        )
        await db.commit()

    game = recruitment["game"]
    timestamp = _iso_to_timestamp(recruitment["scheduled_time"])

    for row in rows:
        try:
            user = await bot.fetch_user(int(row["user_id"]))
            await user.send(
                f"⏰ **{minutes_before}分後**に **{game}** の募集が始まります！\n"
                f"開始予定: <t:{timestamp}:F>"
            )
        except (discord.Forbidden, discord.NotFound):
            print(f"[通知] ユーザー {row['user_id']} へのDM送信失敗（DM無効の可能性）")


async def send_start_mention(bot: discord.Client, recruitment_id: int) -> None:
    """開始時刻にチャンネルで参加者全員をメンション。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM recruitments WHERE id = ?", (recruitment_id,)
        ) as cursor:
            recruitment = await cursor.fetchone()
        if not recruitment or recruitment["status"] != "open":
            return

        async with db.execute(
            "SELECT user_id FROM participants "
            "WHERE recruitment_id = ? AND join_type IN ('confirmed','late','partial')",
            (recruitment_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        await db.execute(
            "UPDATE recruitments SET status = 'closed' WHERE id = ?", (recruitment_id,)
        )
        await db.execute(
            "UPDATE notifications SET sent = 1 "
            "WHERE recruitment_id = ? AND minutes_before = 0",
            (recruitment_id,),
        )
        await db.commit()

    if not rows:
        return

    channel = bot.get_channel(int(recruitment["channel_id"]))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(recruitment["channel_id"]))
        except (discord.Forbidden, discord.NotFound):
            return

    mentions = " ".join(f"<@{row['user_id']}>" for row in rows)
    await channel.send(
        f"🎮 **{recruitment['game']}** の時間になりました！\n{mentions}\nよろしくお願いします！"
    )


def _iso_to_timestamp(iso_str: str) -> int:
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


class Notifications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
