from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import aiosqlite

from database import DB_PATH
from utils.validators import parse_positive_int, parse_time_hhmm
from utils.embed_builder import build_recruit_embed
from scheduler import schedule_notification, schedule_start_mention, cancel_jobs, NOTIFY_MINUTES

JST = timezone(timedelta(hours=9))


# ──────────────────────────────────────────────
# 日時選択 UI
# ──────────────────────────────────────────────

class YearMonthSelect(discord.ui.Select):
    def __init__(self):
        now = datetime.now(JST)
        options = []
        for i in range(12):
            month = (now.month - 1 + i) % 12 + 1
            year = now.year + (now.month - 1 + i) // 12
            options.append(discord.SelectOption(label=f"{year}年{month}月", value=f"{year}-{month:02d}"))
        super().__init__(placeholder="📅 年月を選択...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_year_month = self.values[0]
        await interaction.response.defer()


class DaySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=f"{d}日", value=str(d)) for d in range(1, 32)]
        super().__init__(placeholder="📆 日を選択...", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_day = self.values[0]
        await interaction.response.defer()


class HourSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=f"{h:02d}時", value=str(h)) for h in range(24)]
        super().__init__(placeholder="🕐 時を選択...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_hour = self.values[0]
        await interaction.response.defer()


class MinuteSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="00分", value="0"),
            discord.SelectOption(label="15分", value="15"),
            discord.SelectOption(label="30分", value="30"),
            discord.SelectOption(label="45分", value="45"),
        ]
        super().__init__(placeholder="⏱ 分を選択...", options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_minute = self.values[0]
        await interaction.response.defer()


class NextToRoleButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="次へ ▶", style=discord.ButtonStyle.primary, row=4)

    async def callback(self, interaction: discord.Interaction):
        v = self.view
        if None in (v.selected_year_month, v.selected_day, v.selected_hour, v.selected_minute):
            await interaction.response.send_message("年月・日・時・分をすべて選択してください。", ephemeral=True)
            return

        try:
            year, month = map(int, v.selected_year_month.split("-"))
            dt = datetime(year, month, int(v.selected_day), int(v.selected_hour), int(v.selected_minute), tzinfo=JST)
        except ValueError:
            await interaction.response.send_message("その月にその日付は存在しません。", ephemeral=True)
            return

        if dt <= datetime.now(JST):
            await interaction.response.send_message("過去の日時は指定できません。", ephemeral=True)
            return

        role_view = RoleSelectView(game=v.game, max_players=v.max_players, cancel_deadline=v.cancel_deadline, dt=dt)
        await interaction.response.edit_message(content="参加可能ロールを選んでください（任意）：", view=role_view)


class DateTimeSelectView(discord.ui.View):
    def __init__(self, game: str, max_players: int, cancel_deadline: int):
        super().__init__(timeout=300)
        self.game = game
        self.max_players = max_players
        self.cancel_deadline = cancel_deadline
        self.selected_year_month: str | None = None
        self.selected_day: str | None = None
        self.selected_hour: str | None = None
        self.selected_minute: str | None = None
        self.add_item(YearMonthSelect())
        self.add_item(DaySelect())
        self.add_item(HourSelect())
        self.add_item(MinuteSelect())
        self.add_item(NextToRoleButton())


class RoleSelectMenu(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="🎮 参加可能ロール（選ばなければ全員OK）",
            min_values=0, max_values=1, row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_role = self.values[0] if self.values else None
        await interaction.response.defer()


class ConfirmRecruitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="✅ 確定", style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction: discord.Interaction):
        v = self.view
        role_name = v.selected_role.name if v.selected_role else None
        recruitment_id, embed, recruit_view = await _create_recruitment(
            interaction, v.dt, v.game, v.max_players, role_name, v.cancel_deadline
        )
        await interaction.response.edit_message(content="✅ 募集を作成しました！", view=None, embed=None)
        message = await interaction.channel.send(embed=embed, view=recruit_view)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE recruitments SET message_id = ? WHERE id = ?",
                (str(message.id), recruitment_id),
            )
            await db.commit()


class RoleSelectView(discord.ui.View):
    def __init__(self, game: str, max_players: int, cancel_deadline: int, dt: datetime):
        super().__init__(timeout=300)
        self.game = game
        self.max_players = max_players
        self.cancel_deadline = cancel_deadline
        self.dt = dt
        self.selected_role: discord.Role | None = None
        self.add_item(RoleSelectMenu())
        self.add_item(ConfirmRecruitButton())


# ──────────────────────────────────────────────
# モーダル: 募集作成
# ──────────────────────────────────────────────

class RecruitModal(discord.ui.Modal, title="遊ぶ募集を作成"):
    game = discord.ui.TextInput(
        label="ゲーム名", placeholder="例: Apex Legends", max_length=100, required=True
    )
    max_players_input = discord.ui.TextInput(
        label="最大人数 (空欄=無制限)", placeholder="例: 5", max_length=3, required=False
    )
    cancel_deadline_input = discord.ui.TextInput(
        label="辞退期限 (開始X分前まで、空欄=制限なし)", placeholder="例: 30",
        max_length=4, required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        max_players, err = parse_positive_int(self.max_players_input.value, "最大人数")
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        cancel_deadline, err = parse_positive_int(self.cancel_deadline_input.value, "辞退期限")
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        view = DateTimeSelectView(
            game=self.game.value.strip(),
            max_players=max_players,
            cancel_deadline=cancel_deadline,
        )
        await interaction.response.send_message("開始日時を選んでください：", view=view, ephemeral=True)


# ──────────────────────────────────────────────
# モーダル: 遅れて参加
# ──────────────────────────────────────────────

class LateModal(discord.ui.Modal, title="遅れて参加"):
    reason = discord.ui.TextInput(
        label="理由（任意）", placeholder="例: 仕事が終わり次第参加します",
        max_length=200, required=False
    )

    def __init__(self, recruitment_id: int, original_message: discord.Message):
        super().__init__()
        self.recruitment_id = recruitment_id
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        now_iso = datetime.now(timezone.utc).isoformat()
        reason = self.reason.value.strip() or None

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO participants (recruitment_id, user_id, join_type, reason, joined_at) "
                "VALUES (?, ?, 'late', ?, ?) "
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET "
                "join_type='late', reason=?, available_until=NULL, joined_at=?",
                (self.recruitment_id, str(interaction.user.id), reason, now_iso, reason, now_iso),
            )
            await db.commit()

        embed = await _build_embed_from_db(self.recruitment_id)
        view = RecruitView(self.recruitment_id)
        await self.original_message.edit(embed=embed, view=view)
        await interaction.response.send_message("✅ 遅れて参加として登録しました！", ephemeral=True)


# ──────────────────────────────────────────────
# モーダル: 途中のみ参加
# ──────────────────────────────────────────────

class PartialModal(discord.ui.Modal, title="途中のみ参加"):
    available_until = discord.ui.TextInput(
        label="何時まで参加可能？ (HH:MM)", placeholder="例: 23:00", max_length=5, required=True
    )
    reason = discord.ui.TextInput(
        label="理由（任意）", placeholder="例: 翌日仕事があるので",
        max_length=200, required=False
    )

    def __init__(self, recruitment_id: int, original_message: discord.Message):
        super().__init__()
        self.recruitment_id = recruitment_id
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        available_until, err = parse_time_hhmm(self.available_until.value)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        reason = self.reason.value.strip() or None

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO participants (recruitment_id, user_id, join_type, reason, available_until, joined_at) "
                "VALUES (?, ?, 'partial', ?, ?, ?) "
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET "
                "join_type='partial', reason=?, available_until=?, joined_at=?",
                (self.recruitment_id, str(interaction.user.id), reason, available_until, now_iso,
                 reason, available_until, now_iso),
            )
            await db.commit()

        embed = await _build_embed_from_db(self.recruitment_id)
        view = RecruitView(self.recruitment_id)
        await self.original_message.edit(embed=embed, view=view)
        await interaction.response.send_message("✅ 途中のみ参加として登録しました！", ephemeral=True)


# ──────────────────────────────────────────────
# ボタンコンポーネント
# ──────────────────────────────────────────────

class JoinButton(discord.ui.Button):
    def __init__(self, recruitment_id: int):
        super().__init__(
            label="✅ 参加", style=discord.ButtonStyle.success,
            custom_id=f"recruit:join:{recruitment_id}"
        )
        self.recruitment_id = recruitment_id

    async def callback(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            recruitment = await _fetch_recruitment(db, self.recruitment_id)
            if not recruitment or recruitment["status"] != "open":
                await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
                return
            if not await _check_role(interaction, recruitment["required_role_name"]):
                return
            if not await _check_capacity(interaction, db, self.recruitment_id, recruitment["max_players"]):
                return

            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO participants (recruitment_id, user_id, join_type, joined_at) VALUES (?, ?, 'confirmed', ?) "
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET "
                "join_type='confirmed', reason=NULL, available_until=NULL, joined_at=?",
                (self.recruitment_id, str(interaction.user.id), now_iso, now_iso),
            )
            await db.commit()

        embed = await _build_embed_from_db(self.recruitment_id)
        await interaction.response.edit_message(embed=embed, view=self.view)


class SubButton(discord.ui.Button):
    def __init__(self, recruitment_id: int):
        super().__init__(
            label="🔄 補欠", style=discord.ButtonStyle.secondary,
            custom_id=f"recruit:sub:{recruitment_id}"
        )
        self.recruitment_id = recruitment_id

    async def callback(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            recruitment = await _fetch_recruitment(db, self.recruitment_id)
            if not recruitment or recruitment["status"] != "open":
                await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
                return
            if not await _check_role(interaction, recruitment["required_role_name"]):
                return

            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO participants (recruitment_id, user_id, join_type, joined_at) VALUES (?, ?, 'substitute', ?) "
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET "
                "join_type='substitute', reason=NULL, available_until=NULL, joined_at=?",
                (self.recruitment_id, str(interaction.user.id), now_iso, now_iso),
            )
            await db.commit()

        embed = await _build_embed_from_db(self.recruitment_id)
        await interaction.response.edit_message(embed=embed, view=self.view)


class LateButton(discord.ui.Button):
    def __init__(self, recruitment_id: int):
        super().__init__(
            label="⏰ 遅れて参加", style=discord.ButtonStyle.primary,
            custom_id=f"recruit:late:{recruitment_id}"
        )
        self.recruitment_id = recruitment_id

    async def callback(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            recruitment = await _fetch_recruitment(db, self.recruitment_id)
            if not recruitment or recruitment["status"] != "open":
                await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
                return
            if not await _check_role(interaction, recruitment["required_role_name"]):
                return
        modal = LateModal(self.recruitment_id, interaction.message)
        await interaction.response.send_modal(modal)


class PartialButton(discord.ui.Button):
    def __init__(self, recruitment_id: int):
        super().__init__(
            label="🕐 途中のみ", style=discord.ButtonStyle.primary,
            custom_id=f"recruit:partial:{recruitment_id}"
        )
        self.recruitment_id = recruitment_id

    async def callback(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            recruitment = await _fetch_recruitment(db, self.recruitment_id)
            if not recruitment or recruitment["status"] != "open":
                await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
                return
            if not await _check_role(interaction, recruitment["required_role_name"]):
                return
        modal = PartialModal(self.recruitment_id, interaction.message)
        await interaction.response.send_modal(modal)


class CancelButton(discord.ui.Button):
    def __init__(self, recruitment_id: int):
        super().__init__(
            label="❌ 辞退", style=discord.ButtonStyle.danger,
            custom_id=f"recruit:cancel:{recruitment_id}"
        )
        self.recruitment_id = recruitment_id

    async def callback(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            recruitment = await _fetch_recruitment(db, self.recruitment_id)
            if not recruitment or recruitment["status"] != "open":
                await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
                return
            if not await _check_cancel_deadline(interaction, recruitment):
                return

            await db.execute(
                "DELETE FROM participants WHERE recruitment_id = ? AND user_id = ?",
                (self.recruitment_id, str(interaction.user.id)),
            )
            await db.commit()

        embed = await _build_embed_from_db(self.recruitment_id)
        await interaction.response.edit_message(embed=embed, view=self.view)


# ──────────────────────────────────────────────
# Persistent View
# ──────────────────────────────────────────────

class DeleteButton(discord.ui.Button):
    def __init__(self, recruitment_id: int):
        super().__init__(
            label="🗑️ 削除", style=discord.ButtonStyle.danger,
            custom_id=f"recruit:delete:{recruitment_id}"
        )
        self.recruitment_id = recruitment_id

    async def callback(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            recruitment = await _fetch_recruitment(db, self.recruitment_id)
            if not recruitment:
                await interaction.response.send_message("この募集は既に削除されています。", ephemeral=True)
                return

        is_creator = str(interaction.user.id) == recruitment["creator_id"]
        is_admin = interaction.user.guild_permissions.administrator or \
                   interaction.user.guild_permissions.manage_guild
        if not is_creator and not is_admin:
            await interaction.response.send_message("募集の作成者か管理者のみ削除できます。", ephemeral=True)
            return

        cancel_jobs(self.recruitment_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM participants WHERE recruitment_id = ?", (self.recruitment_id,))
            await db.execute("DELETE FROM notifications WHERE recruitment_id = ?", (self.recruitment_id,))
            await db.execute("DELETE FROM recruitments WHERE id = ?", (self.recruitment_id,))
            await db.commit()

        await interaction.message.delete()


class RecruitView(discord.ui.View):
    def __init__(self, recruitment_id: int):
        super().__init__(timeout=None)
        self.add_item(JoinButton(recruitment_id))
        self.add_item(SubButton(recruitment_id))
        self.add_item(LateButton(recruitment_id))
        self.add_item(PartialButton(recruitment_id))
        self.add_item(CancelButton(recruitment_id))
        self.add_item(DeleteButton(recruitment_id))


# ──────────────────────────────────────────────
# ヘルパー関数
# ──────────────────────────────────────────────

async def _create_recruitment(
    interaction: discord.Interaction,
    scheduled_time: datetime,
    game: str,
    max_players: int,
    required_role_name: str | None,
    cancel_deadline: int,
) -> tuple[int, discord.Embed, "RecruitView"]:
    now_iso = datetime.now(timezone.utc).isoformat()
    scheduled_iso = scheduled_time.isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO recruitments "
            "(guild_id, channel_id, creator_id, game, scheduled_time, max_players, "
            "required_role_name, cancel_deadline_minutes, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (
                str(interaction.guild_id), str(interaction.channel_id),
                str(interaction.user.id), game,
                scheduled_iso, max_players, required_role_name, cancel_deadline, now_iso,
            ),
        )
        recruitment_id = cursor.lastrowid

        for minutes in NOTIFY_MINUTES:
            await db.execute(
                "INSERT INTO notifications (recruitment_id, minutes_before, sent) VALUES (?, ?, 0)",
                (recruitment_id, minutes),
            )
        await db.execute(
            "INSERT INTO notifications (recruitment_id, minutes_before, sent) VALUES (?, 0, 0)",
            (recruitment_id,),
        )
        await db.commit()

    now_utc = datetime.now(timezone.utc)
    for minutes in NOTIFY_MINUTES:
        fire_time = scheduled_time - timedelta(minutes=minutes)
        if fire_time > now_utc:
            schedule_notification(interaction.client, recruitment_id, minutes, fire_time)
    schedule_start_mention(interaction.client, recruitment_id, scheduled_time)

    embed = build_recruit_embed(
        game=game,
        scheduled_time=scheduled_time,
        max_players=max_players,
        required_role_name=required_role_name,
        cancel_deadline=cancel_deadline,
        creator_id=str(interaction.user.id),
        participants=[],
    )
    return recruitment_id, embed, RecruitView(recruitment_id)


async def _fetch_recruitment(db: aiosqlite.Connection, recruitment_id: int):
    async with db.execute("SELECT * FROM recruitments WHERE id = ?", (recruitment_id,)) as cursor:
        return await cursor.fetchone()


async def _check_role(interaction: discord.Interaction, required_role_name: str | None) -> bool:
    if not required_role_name:
        return True
    role = discord.utils.get(interaction.guild.roles, name=required_role_name)
    if not role:
        return True
    if role not in interaction.user.roles:
        await interaction.response.send_message(
            f"この募集は @{required_role_name} のメンバーのみ参加できます。", ephemeral=True
        )
        return False
    return True


async def _check_capacity(
    interaction: discord.Interaction,
    db: aiosqlite.Connection,
    recruitment_id: int,
    max_players: int,
) -> bool:
    if max_players == 0:
        return True
    async with db.execute(
        "SELECT COUNT(*) FROM participants "
        "WHERE recruitment_id = ? AND join_type IN ('confirmed','late','partial')",
        (recruitment_id,),
    ) as cursor:
        count = (await cursor.fetchone())[0]
    if count >= max_players:
        await interaction.response.send_message(
            "定員に達しています。補欠（🔄）として参加することができます。", ephemeral=True
        )
        return False
    return True


async def _check_cancel_deadline(interaction: discord.Interaction, recruitment) -> bool:
    deadline_minutes = recruitment["cancel_deadline_minutes"]
    if deadline_minutes == 0:
        return True
    scheduled = datetime.fromisoformat(recruitment["scheduled_time"])
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    deadline = scheduled - timedelta(minutes=deadline_minutes)
    if datetime.now(timezone.utc) > deadline:
        await interaction.response.send_message(
            f"辞退期限（開始{deadline_minutes}分前）を過ぎているため辞退できません。", ephemeral=True
        )
        return False
    return True


async def _build_embed_from_db(recruitment_id: int) -> discord.Embed:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM recruitments WHERE id = ?", (recruitment_id,)) as cursor:
            recruitment = await cursor.fetchone()
        async with db.execute(
            "SELECT * FROM participants WHERE recruitment_id = ?", (recruitment_id,)
        ) as cursor:
            participants = [dict(p) for p in await cursor.fetchall()]

    scheduled_time = datetime.fromisoformat(recruitment["scheduled_time"])
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

    return build_recruit_embed(
        game=recruitment["game"],
        scheduled_time=scheduled_time,
        max_players=recruitment["max_players"],
        required_role_name=recruitment["required_role_name"],
        cancel_deadline=recruitment["cancel_deadline_minutes"],
        creator_id=recruitment["creator_id"],
        participants=participants,
    )


# ──────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────

class Recruit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="recruit", description="遊ぶメンバーを募集します")
    async def recruit(self, interaction: discord.Interaction):
        print(f"[AsoBot] /recruit called by {interaction.user} in guild {interaction.guild_id}", flush=True)
        await interaction.response.send_modal(RecruitModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(Recruit(bot))
