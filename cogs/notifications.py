from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from database import get_pool


async def send_dm_notification(bot: discord.Client, recruitment_id: int, minutes_before: int) -> None:
    """参加者に開始X分前DM通知を送る（ユーザー設定に合致する人のみ）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        recruitment = await conn.fetchrow(
            "SELECT * FROM recruitments WHERE id = $1", recruitment_id
        )
        if not recruitment or recruitment["status"] != "open":
            return

        rows = await conn.fetch(
            "SELECT user_id FROM participants "
            "WHERE recruitment_id = $1 AND join_type IN ('confirmed','late','partial')",
            recruitment_id,
        )

        await conn.execute(
            "UPDATE notifications SET sent = 1 "
            "WHERE recruitment_id = $1 AND minutes_before = $2",
            recruitment_id, minutes_before,
        )

        user_settings: dict[str, int] = {}
        for row in rows:
            setting = await conn.fetchrow(
                "SELECT notify_minutes FROM user_settings WHERE user_id = $1",
                row["user_id"],
            )
            user_settings[row["user_id"]] = setting["notify_minutes"] if setting else 30

    game = recruitment["game"]
    timestamp = _iso_to_timestamp(recruitment["scheduled_time"])

    for row in rows:
        user_notify = user_settings[row["user_id"]]
        if user_notify == 0 or user_notify != minutes_before:
            continue

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
    pool = await get_pool()
    async with pool.acquire() as conn:
        recruitment = await conn.fetchrow(
            "SELECT * FROM recruitments WHERE id = $1", recruitment_id
        )
        if not recruitment or recruitment["status"] != "open":
            return

        rows = await conn.fetch(
            "SELECT user_id FROM participants "
            "WHERE recruitment_id = $1 AND join_type IN ('confirmed','late','partial')",
            recruitment_id,
        )

        async with conn.transaction():
            await conn.execute(
                "UPDATE recruitments SET status = 'closed' WHERE id = $1", recruitment_id
            )
            await conn.execute(
                "UPDATE notifications SET sent = 1 "
                "WHERE recruitment_id = $1 AND minutes_before = 0",
                recruitment_id,
            )

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

    @app_commands.command(name="notify", description="募集開始前のDM通知タイミングを設定します")
    @app_commands.describe(minutes="通知タイミング（0=オフ）")
    @app_commands.choices(minutes=[
        app_commands.Choice(name="オフ（通知しない）", value=0),
        app_commands.Choice(name="5分前", value=5),
        app_commands.Choice(name="10分前", value=10),
        app_commands.Choice(name="15分前", value=15),
        app_commands.Choice(name="30分前（デフォルト）", value=30),
        app_commands.Choice(name="60分前", value=60),
    ])
    async def notify(self, interaction: discord.Interaction, minutes: int):
        pool = await get_pool()
        await pool.execute(
            "INSERT INTO user_settings (user_id, notify_minutes) VALUES ($1, $2) "
            "ON CONFLICT(user_id) DO UPDATE SET notify_minutes = $2",
            str(interaction.user.id), minutes,
        )

        if minutes == 0:
            msg = "🔕 DM通知をオフにしました。"
        else:
            msg = f"✅ 募集開始 **{minutes}分前** にDM通知を送るように設定しました。"
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
