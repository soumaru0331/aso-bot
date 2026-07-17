from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database import get_pool

DEFAULT_COLOR = 0x5865F2

COLOR_OPTIONS = [
    ("🔵 青", 0x5865F2),
    ("🟢 緑", 0x57F287),
    ("🔴 赤", 0xED4245),
    ("🟡 黄", 0xFEE75C),
    ("🟣 紫", 0x9B59B6),
    ("🟠 オレンジ", 0xE67E22),
    ("🩵 水色", 0x1ABC9C),
    ("🩷 ピンク", 0xFF73FA),
    ("⚪ 白", 0xFFFFFF),
    ("⚫ 黒", 0x2C2F33),
]


def _can_manage_panel(user: discord.Member) -> bool:
    p = user.guild_permissions
    return p.administrator or p.manage_guild or p.manage_roles


async def _toggle_role(interaction: discord.Interaction, role_id: int) -> None:
    """ロールの付与/解除。権限エラーは原因ごとに分かりやすく表示。"""
    try:
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(
                "ロールが見つかりません（削除された可能性があります）。管理者に連絡してください。",
                ephemeral=True,
            )
            return

        me = interaction.guild.me
        if not me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "⚠️ Botに「ロールの管理」権限がありません。\n"
                "サーバー設定 → ロール → aso bot に「ロールの管理」を付与してください。",
                ephemeral=True,
            )
            return
        if role >= me.top_role:
            await interaction.response.send_message(
                f"⚠️ Botのロールが **{role.name}** より下にあるため付与できません。\n"
                "サーバー設定 → ロール で、aso bot のロールを対象ロールより**上**にドラッグしてください。",
                ephemeral=True,
            )
            return
        if role.managed:
            await interaction.response.send_message(
                "このロールは連携管理ロールのため付与できません。", ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"**{role.name}** ロールを外しました。", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ **{role.name}** ロールを付与しました！", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            "⚠️ 権限エラーです。Botのロール位置と「ロールの管理」権限を確認してください。",
            ephemeral=True,
        )
    except Exception as e:
        print(f"[PanelToggleRole] エラー: {e}", flush=True)
        try:
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)
        except Exception:
            pass


# ──────────────────────────────────────────────
# Persistent View 用ボタン
# ──────────────────────────────────────────────

class RulesAgreeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"panel:rules:(?P<panel_id>\d+):(?P<role_id>\d+)",
):
    """custom_idパターンで動くためBot再起動・デプロイのタイミングに関係なく常に反応する。"""

    def __init__(self, panel_id: int, role_id: int, label: str = "✅ 同意してロールを受け取る"):
        super().__init__(discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=f"panel:rules:{panel_id}:{role_id}",
            row=0,
        ))
        self.panel_id = panel_id
        self.role_id = role_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["panel_id"]), int(match["role_id"]))

    async def callback(self, interaction: discord.Interaction):
        await _toggle_role(interaction, self.role_id)


class RoleToggleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"panel:role:(?P<panel_id>\d+):(?P<role_id>\d+)",
):
    def __init__(self, panel_id: int, role_id: int, label: str = "ロール", row: int = 0):
        super().__init__(discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"panel:role:{panel_id}:{role_id}",
            row=row,
        ))
        self.panel_id = panel_id
        self.role_id = role_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["panel_id"]), int(match["role_id"]))

    async def callback(self, interaction: discord.Interaction):
        await _toggle_role(interaction, self.role_id)


class PanelEditModal(discord.ui.Modal, title="パネルを編集"):
    def __init__(self, panel_id: int, current_title: str, current_body: str | None,
                 panel_type: str, color: int, button_label: str | None = None,
                 message: discord.Message | None = None):
        super().__init__()
        self.panel_id = panel_id
        self.panel_type = panel_type
        self.color = color
        self.message = message
        self.new_title = discord.ui.TextInput(
            label="パネルタイトル", default=current_title, max_length=100
        )
        self.new_body = discord.ui.TextInput(
            label="本文", default=current_body or "", max_length=1500,
            style=discord.TextStyle.paragraph, required=(panel_type != "role")
        )
        self.add_item(self.new_title)
        self.add_item(self.new_body)
        self.new_button_label = None
        if panel_type == "rules":
            self.new_button_label = discord.ui.TextInput(
                label="ボタンのテキスト", default=button_label or "✅ 同意してロールを受け取る",
                max_length=80, required=False
            )
            self.add_item(self.new_button_label)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            label = None
            if self.new_button_label is not None:
                label = self.new_button_label.value.strip() or "✅ 同意してロールを受け取る"
            view = PanelEditSetupView(
                panel_id=self.panel_id,
                panel_type=self.panel_type,
                message=self.message or interaction.message,
                new_title=self.new_title.value.strip(),
                new_body=self.new_body.value.strip() or None,
                new_button_label=label,
                current_color=self.color,
            )
            await interaction.response.send_message(
                "🎨 色やロールも変える場合は選択してください。そのままなら「✅ 更新」：",
                view=view, ephemeral=True,
            )
        except Exception as e:
            print(f"[PanelEditModal] エラー: {e}", flush=True)
            try:
                await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
            except Exception:
                pass


class PanelEditSetupView(discord.ui.View):
    """編集2段階目: 色・ロールの選び直し（任意）→ 更新確定。"""

    def __init__(self, panel_id: int, panel_type: str, message: discord.Message,
                 new_title: str, new_body: str | None, new_button_label: str | None,
                 current_color: int):
        super().__init__(timeout=300)
        self.panel_id = panel_id
        self.panel_type = panel_type
        self.message = message
        self.new_title = new_title
        self.new_body = new_body
        self.new_button_label = new_button_label
        self.color = current_color
        self.selected_roles: list[discord.Role] | None = None  # None = 変更なし
        self.add_item(ColorSelect(row=0))
        if panel_type == "rules":
            self.add_item(self._make_role_select("🔑 付与ロールを変更...（変更しない場合は触らない）", 1))
        elif panel_type == "role":
            self.add_item(self._make_role_select("🔑 ロール構成を選び直す...（変更しない場合は触らない）", 20))
        self.add_item(self._make_confirm())

    def _make_role_select(self, placeholder: str, max_values: int):
        select = discord.ui.RoleSelect(
            placeholder=placeholder, min_values=0, max_values=max_values, row=1
        )
        async def cb(interaction: discord.Interaction):
            self.selected_roles = list(select.values) if select.values else None
            await interaction.response.defer()
        select.callback = cb
        return select

    def _make_confirm(self):
        btn = discord.ui.Button(label="✅ 更新", style=discord.ButtonStyle.success, row=2)
        async def cb(interaction: discord.Interaction):
            try:
                await _apply_panel_edit(interaction, self)
            except Exception as e:
                print(f"[PanelEditSetup] エラー: {e}", flush=True)
                try:
                    await interaction.response.send_message("更新に失敗しました。", ephemeral=True)
                except Exception:
                    pass
        btn.callback = cb
        return btn


async def _apply_panel_edit(interaction: discord.Interaction, v: PanelEditSetupView):
    pool = await get_pool()
    await pool.execute(
        "UPDATE role_panels SET title = $1, description = $2, color = $3 WHERE id = $4",
        v.new_title, v.new_body, v.color, v.panel_id,
    )

    embed = discord.Embed(title=v.new_title, description=v.new_body, color=v.color)
    new_view: discord.ui.View

    if v.panel_type == "rules":
        if v.selected_roles:
            await pool.execute("DELETE FROM role_panel_buttons WHERE panel_id = $1", v.panel_id)
            await pool.execute(
                "INSERT INTO role_panel_buttons (panel_id, role_id, label) VALUES ($1, $2, $3)",
                v.panel_id, str(v.selected_roles[0].id),
                v.new_button_label or "✅ 同意してロールを受け取る",
            )
        elif v.new_button_label is not None:
            await pool.execute(
                "UPDATE role_panel_buttons SET label = $1 WHERE panel_id = $2",
                v.new_button_label, v.panel_id,
            )
        btn_row = await pool.fetchrow(
            "SELECT role_id, label FROM role_panel_buttons WHERE panel_id = $1", v.panel_id
        )
        new_view = RulesView(v.panel_id, int(btn_row["role_id"]), btn_row["label"])

    elif v.panel_type == "role":
        embed.set_footer(text="ボタンをもう一度押すとロールが外れます")
        if v.selected_roles:
            await pool.execute("DELETE FROM role_panel_buttons WHERE panel_id = $1", v.panel_id)
            for role in v.selected_roles[:20]:
                await pool.execute(
                    "INSERT INTO role_panel_buttons (panel_id, role_id, label) VALUES ($1, $2, $3)",
                    v.panel_id, str(role.id), role.name,
                )
        buttons = await pool.fetch(
            "SELECT role_id, label FROM role_panel_buttons WHERE panel_id = $1", v.panel_id
        )
        new_view = RolePanelView(v.panel_id, [dict(b) for b in buttons])

    else:
        new_view = TextPanelView(v.panel_id)

    await v.message.edit(embed=embed, view=new_view)
    await interaction.response.edit_message(content="✅ パネルを更新しました！", view=None)


class PanelEditButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"panel:edit:(?P<panel_id>\d+)",
):
    def __init__(self, panel_id: int, row: int = 0):
        super().__init__(discord.ui.Button(
            label="✏️ 編集",
            style=discord.ButtonStyle.secondary,
            custom_id=f"panel:edit:{panel_id}",
            row=row,
        ))
        self.panel_id = panel_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["panel_id"]))

    async def callback(self, interaction: discord.Interaction):
        try:
            if not _can_manage_panel(interaction.user):
                await interaction.response.send_message(
                    "パネルの編集は管理者（ロールの管理権限）のみ可能です。", ephemeral=True
                )
                return
            pool = await get_pool()
            panel = await pool.fetchrow(
                "SELECT title, description, panel_type, color FROM role_panels WHERE id = $1",
                self.panel_id,
            )
            if not panel:
                await interaction.response.send_message("このパネルはDBに存在しません。", ephemeral=True)
                return
            button_label = None
            if panel["panel_type"] == "rules":
                btn_row = await pool.fetchrow(
                    "SELECT label FROM role_panel_buttons WHERE panel_id = $1",
                    self.panel_id,
                )
                if btn_row:
                    button_label = btn_row["label"]
            await interaction.response.send_modal(PanelEditModal(
                self.panel_id, panel["title"], panel["description"],
                panel["panel_type"], panel["color"], button_label,
                message=interaction.message,
            ))
        except Exception as e:
            print(f"[PanelEditButton] エラー: {e}", flush=True)


class PanelDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"panel:delete:(?P<panel_id>\d+)",
):
    def __init__(self, panel_id: int, row: int = 0):
        super().__init__(discord.ui.Button(
            label="🗑 パネル削除",
            style=discord.ButtonStyle.secondary,
            custom_id=f"panel:delete:{panel_id}",
            row=row,
        ))
        self.panel_id = panel_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["panel_id"]))

    async def callback(self, interaction: discord.Interaction):
        try:
            if not _can_manage_panel(interaction.user):
                await interaction.response.send_message(
                    "パネルの削除は管理者（ロールの管理権限）のみ可能です。", ephemeral=True
                )
                return
            pool = await get_pool()
            await pool.execute("DELETE FROM role_panel_buttons WHERE panel_id = $1", self.panel_id)
            await pool.execute("DELETE FROM role_panels WHERE id = $1", self.panel_id)
            await interaction.message.delete()
        except Exception as e:
            print(f"[PanelDeleteButton] エラー: {e}", flush=True)
            try:
                await interaction.response.send_message("削除に失敗しました。", ephemeral=True)
            except Exception:
                pass


class RulesView(discord.ui.View):
    def __init__(self, panel_id: int, role_id: int, button_label: str | None = None):
        super().__init__(timeout=None)
        self.add_item(RulesAgreeButton(panel_id, role_id, button_label or "✅ 同意してロールを受け取る"))
        self.add_item(PanelEditButton(panel_id, row=1))
        self.add_item(PanelDeleteButton(panel_id, row=1))


class RolePanelView(discord.ui.View):
    def __init__(self, panel_id: int, buttons: list[dict]):
        super().__init__(timeout=None)
        for i, b in enumerate(buttons[:20]):
            self.add_item(RoleToggleButton(
                panel_id=panel_id,
                role_id=int(b["role_id"]),
                label=b["label"],
                row=i // 5,
            ))
        self.add_item(PanelEditButton(panel_id, row=4))
        self.add_item(PanelDeleteButton(panel_id, row=4))


class TextPanelView(discord.ui.View):
    def __init__(self, panel_id: int):
        super().__init__(timeout=None)
        self.add_item(PanelEditButton(panel_id, row=0))
        self.add_item(PanelDeleteButton(panel_id, row=0))


# ──────────────────────────────────────────────
# 共通: 色選択 Select
# ──────────────────────────────────────────────

class ColorSelect(discord.ui.Select):
    def __init__(self, row: int = 0):
        options = [
            discord.SelectOption(label=name, value=str(value))
            for name, value in COLOR_OPTIONS
        ]
        super().__init__(placeholder="🎨 パネルの色を選択（選ばなければ青）", options=options,
                         min_values=0, max_values=1, row=row)

    async def callback(self, interaction: discord.Interaction):
        if self.values:
            self.view.color = int(self.values[0])
        await interaction.response.defer()


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
        label="ボタンのテキスト", default="✅ 同意してロールを受け取る", max_length=80,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        view = RulesSetupView(
            title=self.panel_title.value.strip(),
            rules_text=self.rules_text.value.strip(),
            button_label=self.button_label.value.strip() or "✅ 同意してロールを受け取る",
        )
        await interaction.response.send_message(
            "🎨 色と、同意したときに付与するロールを選んでください：", view=view, ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[RulesModal] on_error: {error}", flush=True)
        try:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        except Exception:
            pass


class RulesSetupView(discord.ui.View):
    def __init__(self, title: str, rules_text: str, button_label: str):
        super().__init__(timeout=300)
        self.title = title
        self.rules_text = rules_text
        self.button_label = button_label
        self.color = DEFAULT_COLOR
        self.selected_role: discord.Role | None = None
        self.add_item(ColorSelect(row=0))
        self.add_item(self._make_role_select())
        self.add_item(self._make_confirm())

    def _make_role_select(self):
        select = discord.ui.RoleSelect(
            placeholder="🔑 付与するロールを選択...", min_values=1, max_values=1, row=1
        )
        async def cb(interaction: discord.Interaction):
            self.selected_role = select.values[0]
            await interaction.response.defer()
        select.callback = cb
        return select

    def _make_confirm(self):
        btn = discord.ui.Button(label="✅ パネルを作成", style=discord.ButtonStyle.success, row=2)
        async def cb(interaction: discord.Interaction):
            if not self.selected_role:
                await interaction.response.send_message("ロールを選んでください。", ephemeral=True)
                return
            try:
                await _post_rules_panel(interaction, self)
            except Exception as e:
                print(f"[RulesSetup] エラー: {e}", flush=True)
                try:
                    await interaction.response.send_message("パネル作成に失敗しました。", ephemeral=True)
                except Exception:
                    pass
        btn.callback = cb
        return btn


async def _post_rules_panel(interaction: discord.Interaction, v: RulesSetupView):
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
    panel_view = RulesView(panel_id, v.selected_role.id, v.button_label)
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
        label="説明文（任意）", placeholder="好きなゲームのロールをボタンで選んでください。",
        style=discord.TextStyle.paragraph, max_length=500, required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        view = RolePanelSetupView(
            title=self.panel_title.value.strip(),
            description=self.description.value.strip(),
        )
        await interaction.response.send_message(
            "🎨 色と、ボタンにするロール（最大20個）を選んでください：", view=view, ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[RolePanelModal] on_error: {error}", flush=True)
        try:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        except Exception:
            pass


class RolePanelSetupView(discord.ui.View):
    def __init__(self, title: str, description: str):
        super().__init__(timeout=300)
        self.title = title
        self.description = description
        self.color = DEFAULT_COLOR
        self.selected_roles: list[discord.Role] = []
        self.add_item(ColorSelect(row=0))
        self.add_item(self._make_role_select())
        self.add_item(self._make_confirm())

    def _make_role_select(self):
        select = discord.ui.RoleSelect(
            placeholder="🔑 ロールを選択...（複数可）", min_values=1, max_values=20, row=1
        )
        async def cb(interaction: discord.Interaction):
            self.selected_roles = select.values
            await interaction.response.defer()
        select.callback = cb
        return select

    def _make_confirm(self):
        btn = discord.ui.Button(label="✅ パネルを作成", style=discord.ButtonStyle.success, row=2)
        async def cb(interaction: discord.Interaction):
            if not self.selected_roles:
                await interaction.response.send_message("ロールを選んでください。", ephemeral=True)
                return
            try:
                await _post_role_panel(interaction, self)
            except Exception as e:
                print(f"[RolePanelSetup] エラー: {e}", flush=True)
                try:
                    await interaction.response.send_message("パネル作成に失敗しました。", ephemeral=True)
                except Exception:
                    pass
        btn.callback = cb
        return btn


async def _post_role_panel(interaction: discord.Interaction, v: RolePanelSetupView):
    now_iso = datetime.now(timezone.utc).isoformat()
    pool = await get_pool()

    panel_id = await pool.fetchval(
        "INSERT INTO role_panels (guild_id, channel_id, panel_type, title, description, color, created_at) "
        "VALUES ($1, $2, 'role', $3, $4, $5, $6) RETURNING id",
        str(interaction.guild_id), str(interaction.channel_id),
        v.title, v.description or None, v.color, now_iso,
    )

    buttons = []
    for role in v.selected_roles[:20]:
        await pool.execute(
            "INSERT INTO role_panel_buttons (panel_id, role_id, label) VALUES ($1, $2, $3)",
            panel_id, str(role.id), role.name,
        )
        buttons.append({"role_id": str(role.id), "label": role.name})

    embed = discord.Embed(title=v.title, color=v.color)
    if v.description:
        embed.description = v.description
    embed.set_footer(text="ボタンをもう一度押すとロールが外れます")

    panel_view = RolePanelView(panel_id, buttons)
    message = await interaction.channel.send(embed=embed, view=panel_view)

    await pool.execute(
        "UPDATE role_panels SET message_id = $1 WHERE id = $2",
        str(message.id), panel_id,
    )
    await interaction.response.edit_message(content="✅ ロールパネルを作成しました！", view=None)


# ──────────────────────────────────────────────
# テキストパネル（お知らせ用）作成フロー
# ──────────────────────────────────────────────

class TextPanelModal(discord.ui.Modal, title="パネルを作成"):
    panel_title = discord.ui.TextInput(
        label="パネルタイトル", placeholder="例: 📢 お知らせ", max_length=100
    )
    body = discord.ui.TextInput(
        label="本文", placeholder="パネルに表示する内容を入力...",
        style=discord.TextStyle.paragraph, max_length=1500
    )

    async def on_submit(self, interaction: discord.Interaction):
        view = TextPanelSetupView(
            title=self.panel_title.value.strip(),
            body=self.body.value.strip(),
        )
        await interaction.response.send_message(
            "🎨 パネルの色を選んでください：", view=view, ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[TextPanelModal] on_error: {error}", flush=True)
        try:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        except Exception:
            pass


class TextPanelSetupView(discord.ui.View):
    def __init__(self, title: str, body: str):
        super().__init__(timeout=300)
        self.title = title
        self.body = body
        self.color = DEFAULT_COLOR
        self.add_item(ColorSelect(row=0))
        self.add_item(self._make_confirm())

    def _make_confirm(self):
        btn = discord.ui.Button(label="✅ パネルを作成", style=discord.ButtonStyle.success, row=1)
        async def cb(interaction: discord.Interaction):
            try:
                await _post_text_panel(interaction, self)
            except Exception as e:
                print(f"[TextPanelSetup] エラー: {e}", flush=True)
                try:
                    await interaction.response.send_message("パネル作成に失敗しました。", ephemeral=True)
                except Exception:
                    pass
        btn.callback = cb
        return btn


async def _post_text_panel(interaction: discord.Interaction, v: TextPanelSetupView):
    now_iso = datetime.now(timezone.utc).isoformat()
    pool = await get_pool()

    panel_id = await pool.fetchval(
        "INSERT INTO role_panels (guild_id, channel_id, panel_type, title, description, color, created_at) "
        "VALUES ($1, $2, 'text', $3, $4, $5, $6) RETURNING id",
        str(interaction.guild_id), str(interaction.channel_id),
        v.title, v.body, v.color, now_iso,
    )

    embed = discord.Embed(title=v.title, description=v.body, color=v.color)
    panel_view = TextPanelView(panel_id)
    message = await interaction.channel.send(embed=embed, view=panel_view)

    await pool.execute(
        "UPDATE role_panels SET message_id = $1 WHERE id = $2",
        str(message.id), panel_id,
    )
    await interaction.response.edit_message(content="✅ パネルを作成しました！", view=None)


# ──────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────

class Panel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rulespanel", description="ルールを表示して同意したユーザーにロールを付与するパネルを作成します")
    @app_commands.default_permissions(manage_roles=True)
    async def rulespanel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RulesModal())

    @app_commands.command(name="rolepanel", description="ボタンでロールを自由に選べるパネルを作成します")
    @app_commands.default_permissions(manage_roles=True)
    async def rolepanel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RolePanelModal())

    @app_commands.command(name="panel", description="色付きのお知らせパネルを作成します（編集可能）")
    @app_commands.default_permissions(manage_roles=True)
    async def panel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TextPanelModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(Panel(bot))
