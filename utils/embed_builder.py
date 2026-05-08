import discord
from datetime import datetime


def build_recruit_embed(
    game: str,
    scheduled_time: datetime,
    max_players: int,
    required_role_name: str | None,
    cancel_deadline: int,
    creator_id: str,
    participants: list[dict],
) -> discord.Embed:
    confirmed = [p for p in participants if p["join_type"] == "confirmed"]
    substitutes = [p for p in participants if p["join_type"] == "substitute"]
    late = [p for p in participants if p["join_type"] == "late"]
    partial = [p for p in participants if p["join_type"] == "partial"]

    player_count = len(confirmed) + len(late) + len(partial)
    max_str = f"/{max_players}" if max_players > 0 else ""

    embed = discord.Embed(title=f"🎮 {game} 募集", color=discord.Color.blue())
    embed.add_field(
        name="📅 開始時刻",
        value=f"<t:{int(scheduled_time.timestamp())}:F>",
        inline=False,
    )
    embed.add_field(name="👥 参加者", value=f"{player_count}{max_str}名", inline=True)
    embed.add_field(
        name="🔒 参加条件",
        value=f"@{required_role_name} のみ" if required_role_name else "全員OK",
        inline=True,
    )
    embed.add_field(
        name="⏰ 辞退期限",
        value=f"開始{cancel_deadline}分前まで" if cancel_deadline > 0 else "制限なし",
        inline=True,
    )
    embed.add_field(name="📋 作成者", value=f"<@{creator_id}>", inline=True)

    if confirmed:
        embed.add_field(
            name=f"✅ 参加 ({len(confirmed)})",
            value="\n".join(f"<@{p['user_id']}>" for p in confirmed),
            inline=False,
        )
    if substitutes:
        embed.add_field(
            name=f"🔄 補欠 ({len(substitutes)})",
            value="\n".join(f"<@{p['user_id']}>" for p in substitutes),
            inline=False,
        )
    if late:
        lines = [
            f"<@{p['user_id']}>" + (f" ({p['reason']})" if p.get("reason") else "")
            for p in late
        ]
        embed.add_field(name=f"⏰ 遅れて参加 ({len(late)})", value="\n".join(lines), inline=False)
    if partial:
        lines = []
        for p in partial:
            line = f"<@{p['user_id']}>"
            if p.get("available_until"):
                line += f" ~{p['available_until']}"
            if p.get("reason"):
                line += f" ({p['reason']})"
            lines.append(line)
        embed.add_field(name=f"🕐 途中のみ ({len(partial)})", value="\n".join(lines), inline=False)

    return embed
