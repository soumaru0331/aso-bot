from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database import get_pool

# カラー名 → int
COLOR_MAP = {
    "青": 0x5865F2,
    "緑": 0x57F287,
    "赤": 0xED4245,
    "黄": 0xFEE75C,
    "紫": 0x9B59B6,
    "オレンジ": 0xE67E22,
    "水色": 0x1ABC9C,
    "ピンク": 0xFF73FA,
    "白": 0xFFFFFF,
    "黒": 0x2C2F33,
}
COLOR_CHOICES = [app_commands.Choice(name=k, value=str(v)) for k, v in COLOR_MAP.items()]


# ──────────────────────────────────────────────
# Persistent Views
# ──────────────────────────────────────────────

class RulesAgreeButton(discord.ui.Button):
    def __init__(self, panel_id: int, role_id: int):
        super().__init__(
            label="✅ 同意してロールを受け取る",
            style=discord.ButtonStyle.success,
            custom_id=f"panel:rules:{panel_id}:{role_id}",
        )
        self.panel_id = panel_id
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        try:
            role = interaction.guild.get_role(self.role_id)
            if not role:
                await interaction.response.send_message("ロールが見つかりません。管理者に連絡してください。", ephemeral=True)
                return
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"**{role.name}** ロールを外しました。", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ **{role.name}** ロールを付与しました！", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("ロールを付与する権限がありません。Bot のロール位置を確認してください。", ephemeral=True)
        except Exception as e:
            print(f"[RulesAgreeButton] エラー: {e}", flush=True)
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)


class RulesView(discord.ui.View):
    def __init__(self, panel_id: int, role_id: int):
        super().__init__(timeout=None)
        self.add_item(RulesAgreeButton(panel_id, role_id))


class RoleToggleButton(discord.ui.Button):
    def __init__(self, panel_id: int, role_id: int, label: str, row: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"panel:role:{panel_id}:{role_id}",
            row=row,
        )
        self.panel_id = panel_id
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        try:
            role = interaction.guild.get_role(self.role_id)
            if not role:
                await interaction.response.send_message("ロールが見つかりません。管理者に連絡してください。", ephemeral=True)
                return
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"**{role.name}** ロールを外しました。", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ **{role.name}** ロールを付与しました！", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("ロールを付与する権限がありません。Bot のロール位置を確認してください。", ephemeral=True)
        except Exception as e:
            print(f"[RoleToggleButton] エラー: {e}", flush=True)
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)


class RolePanelView(discord.ui.View):
    def __init__(self, panel_id: int, buttons: list[dict]):
        super().__init__(timeout=None)
        for i, b in enumerate(buttons):
            self.add_item(RoleToggleButton(
                panel_id=panel_id,
                role_id=int(b["role_id"]),
                label=b["label"],
                row=i // 5,
            ))


# ──────────────────────────────────────────────
# ルールパネル作成フロー
# ──────────────────────────────────────────────

class RulesModal(discord.ui.Modal, title="ルールパネルを作成"):
    panel_title = discord.ui.TextInput(
        label="パネルタイトル", placeholder="例: サーバールール", max_length=100
    )
    rules_text = discord.ui.TextInput(
        label="ルール本文", placeholder="1. 荒らし禁止\n2. 差別的発言禁止\n...",
        style=discord.TextStyle.paragraph, max_length=1500
    )
    button_label = discord.ui.TextInput(
        label="ボタンのテキスト", placeholder="✅ 同意してロールを受け取る",
        default="✅ 同意してロールを受け取る", max_length=80
    )

    def __init__(self, color: int):
        super().__init__()
        self.color = color

    async def on_submit(self, interaction: discord.Interaction):
        view = RulesRoleSelectView(
            title=self.panel_title.value.strip(),
            rules_text=self.rules_text.value.strip(),
            button_label=self.button_label.value.strip(),
            color=self.color,
        )
        await interaction.response.send_message(
            "同意したときに付与するロールを選んでください：", view=view, ephemeral=True
        )


class RulesRoleSelectView(discord.ui.View):
    def __init__(self, title: str, rules_text: str, button_label: str, color: int):
        super().__init__(timeout=180)
        self.title = title
        self.rules_text = rules_text
        self.button_label = button_label
        self.color = color
        self.selected_role: discord.Role | None = None
        self.add_item(self._make_role_select())
        self.add_item(self._make_confirm())

    def _make_role_select(self):
        select = discord.ui.RoleSelect(
            placeholder="付与するロールを選択...", min_values=1, max_values=1, row=0
        )
        async def cb(interaction: discord.Interaction):
            self.selected_role = select.values[0]
            await interaction.response.defer()
        select.callback = cb
        return select

    def _make_confirm(self):
        btn = discord.ui.Button(label="✅ パネルを作成", style=discord.ButtonStyle.success, row=1)
        async def cb(interaction: discord.Interaction):
            if not self.selected_role:
                await interaction.response.send_message("ロールを選んでください。", ephemeral=True)
                return
            await _post_rules_panel(interaction, self)
        btn.callback = cb
        return btn


async def _post_rules_panel(interaction: discord.Interaction, v: RulesRoleSelectView):
    now_iso = datetime.now(timezone.utc).isoformat()
    pool = await get_pool()

    panel_id = await pool.fetchval(
        "INSERT INTO role_panels (guild_id, channel_id, panel_type, title, description, color, created_at) "
        "VALUES ($1, $2, 'rules', $3, $4, $5, $6) RETURNING id",
        str(interaction.guild_id), str(interaction.channel_id),
        v.title, v.rules_text, v.color, now_iso,
    )
    await pool.execute(
        "INSERT INTO role_panel_buttons (panel_id, role_id, label) VALUES ($1, $2, $3)",
        panel_id, str(v.selected_role.id), v.button_label,
    )

    embed = discord.Embed(title=v.title, description=v.rules_text, color=v.color)
    embed.set_footer(text="ボタンを押すともう一度押すと外れます")
    panel_view = RulesView(panel_id, v.selected_role.id)
    message = await interaction.channel.send(embed=embed, view=panel_view)

    await pool.execute(
        "UPDATE role_panels SET message_id = $1 WHERE id = $2",
        str(message.id), panel_id,
    )
    await interaction.response.edit_message(content="✅ ルールパネルを作成しました！", view=None)


# ──────────────────────────────────────────────
# ロール選択パネル作成フロー
# ──────────────────────────────────────────────

class RolePanelModal(discord.ui.Modal, title="ロールパネルを作成"):
    panel_title = discord.ui.TextInput(
        label="パネルタイトル", placeholder="例: ゲームロールを選ぼう！", max_length=100
    )
    description = discord.ui.TextInput(
        label="説明文", placeholder="好きなゲームのロールをボタンで選んでください。",
        style=discord.TextStyle.paragraph, max_length=500, required=False
    )

    def __init__(self, color: int):
        super().__init__()
        self.color = color

    async def on_submit(self, interaction: discord.Interaction):
        view = RolePanelRoleSelectView(
            title=self.panel_title.value.strip(),
            description=self.description.value.strip(),
            color=self.color,
        )
        await interaction.response.send_message(
            "ボタンにするロールを選んでください（最大20個）：", view=view, ephemeral=True
        )


class RolePanelRoleSelectView(discord.ui.View):
    def __init__(self, title: str, description: str, color: int):
        super().__init__(timeout=180)
        self.title = title
        self.description = description
        self.color = color
        self.selected_roles: list[discord.Role] = []
        self.add_item(self._make_role_select())
        self.add_item(self._make_confirm())

    def _make_role_select(self):
        select = discord.ui.RoleSelect(
            placeholder="ロールを選択...（複数可）", min_values=1, max_values=20, row=0
        )
        async def cb(interaction: discord.Interaction):
            self.selected_roles = select.values
            await interaction.response.defer()
        select.callback = cb
        return select

    def _make_confirm(self):
        btn = discord.ui.Button(label="✅ パネルを作成", style=discord.ButtonStyle.success, row=1)
        async def cb(interaction: discord.Interaction):
            if not self.selected_roles:
                await interaction.response.send_message("ロールを選んでください。", ephemeral=True)
                return
            if len(self.selected_roles) > 20:
                await interaction.response.send_message("ロールは20個までです。", ephemeral=True)
                return
            await _post_role_panel(interaction, self)
        btn.callback = cb
        return btn


async def _post_role_panel(interaction: discord.Interaction, v: RolePanelRoleSelectView):
    now_iso = datetime.now(timezone.utc).isoformat()
    pool = await get_pool()

    panel_id = await pool.fetchval(
        "INSERT INTO role_panels (guild_id, channel_id, panel_type, title, description, color, created_at) "
        "VALUES ($1, $2, 'role', $3, $4, $5, $6) RETURNING id",
        str(interaction.guild_id), str(interaction.channel_id),
        v.title, v.description or None, v.color, now_iso,
    )

    buttons = []
    for role in v.selected_roles:
        await pool.execute(
            "INSERT INTO role_panel_buttons (panel_id, role_id, label) VALUES ($1, $2, $3)",
            panel_id, str(role.id), role.name,
        )
        buttons.append({"role_id": str(role.id), "label": role.name})

    embed = discord.Embed(title=v.title, color=v.color)
    if v.description:
        embed.description = v.description
    embed.set_footer(text="ボタンを押すともう一度押すと外れます")

    panel_view = RolePanelView(panel_id, buttons)
    message = await interaction.channel.send(embed=embed, view=panel_view)

    await pool.execute(
        "UPDATE role_panels SET message_id = $1 WHERE id = $2",
        str(message.id), panel_id,
    )
    await interaction.response.edit_message(content="✅ ロールパネルを作成しました！", view=None)


# ──────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────

class Panel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rulespanel", description="ルールを表示して同意したユーザーにロールを付与するパネルを作成します")
    @app_commands.describe(color="パネルの色")
    @app_commands.choices(color=COLOR_CHOICES)
    @app_commands.default_permissions(manage_roles=True)
    async def rulespanel(self, interaction: discord.Interaction, color: str = str(0x5865F2)):
        await interaction.response.send_modal(RulesModal(color=int(color)))

    @app_commands.command(name="rolepanel", description="ボタンでロールを自由に選べるパネルを作成します")
    @app_commands.describe(color="パネルの色")
    @app_commands.choices(color=COLOR_CHOICES)
    @app_commands.default_permissions(manage_roles=True)
    async def rolepanel(self, interaction: discord.Interaction, color: str = str(0x5865F2)):
        await interaction.response.send_modal(RolePanelModal(color=int(color)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Panel(bot))
