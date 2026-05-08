# Discord 遊ぶ募集Bot 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スラッシュコマンドでゲーム遊ぶ募集を作成・管理し、DM通知と開始時メンションを行うDiscord Botを構築する。

**Architecture:** Python + discord.py 2.x のシンプル単体Bot。機能をCogで分割し、SQLiteでデータ永続化、APSchedulerでタイマー管理。ボタンはdiscord.pyのPersistent Viewパターンで実装しBotリスタート後も動作継続。

**Tech Stack:** Python 3.11+, discord.py 2.x, aiosqlite, APScheduler 3.x, python-dotenv, pytest, pytest-asyncio

---

## ファイル構成

```
aso-bot/
├── main.py                    # Bot起動・Cog読み込み・Persistent View登録
├── config.py                  # .envからトークン読み込み
├── database.py                # SQLite初期化・共通接続
├── scheduler.py               # APScheduler管理
├── cogs/
│   ├── recruit.py             # /recruit コマンド・Modal・Button・Embed
│   └── notifications.py       # DM通知・開始時メンション関数
├── utils/
│   ├── validators.py          # 入力バリデーション（純粋関数）
│   └── embed_builder.py       # Embed生成（純粋関数）
├── models/
│   └── schema.sql             # DBスキーマ
├── tests/
│   ├── test_validators.py
│   ├── test_embed_builder.py
│   └── test_database.py
├── setup.sh                   # Oracle Cloud デプロイスクリプト
├── CLAUDE.md                  # 次回セッション用プロジェクト概要
├── .env                       # トークン（git管理外）
├── .env.example               # テンプレート
├── .gitignore
└── requirements.txt
```

---

## Task 1: プロジェクトスキャフォルド

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `models/schema.sql`

- [ ] **Step 1: requirements.txt を作成**

```
discord.py==2.3.2
aiosqlite==0.20.0
APScheduler==3.10.4
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.7
```

- [ ] **Step 2: .env.example を作成**

```
DISCORD_TOKEN=your_token_here
DB_PATH=bot.db
```

- [ ] **Step 3: .gitignore を作成**

```
.env
bot.db
__pycache__/
*.py[cod]
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 4: models/schema.sql を作成**

```sql
CREATE TABLE IF NOT EXISTS recruitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_id TEXT,
    creator_id TEXT NOT NULL,
    game TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    max_players INTEGER NOT NULL DEFAULT 0,
    required_role_name TEXT,
    cancel_deadline_minutes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recruitment_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    join_type TEXT NOT NULL,
    reason TEXT,
    available_until TEXT,
    joined_at TEXT NOT NULL,
    UNIQUE(recruitment_id, user_id),
    FOREIGN KEY(recruitment_id) REFERENCES recruitments(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recruitment_id INTEGER NOT NULL,
    minutes_before INTEGER NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(recruitment_id) REFERENCES recruitments(id)
);
```

- [ ] **Step 5: ディレクトリ作成**

```bash
mkdir -p cogs utils tests models
touch cogs/__init__.py utils/__init__.py tests/__init__.py
```

- [ ] **Step 6: 依存インストール**

```bash
pip install -r requirements.txt
```

Expected: Successfully installed discord.py-2.3.2 aiosqlite-0.20.0 APScheduler-3.10.4 python-dotenv-1.0.1 pytest-8.2.0 pytest-asyncio-0.23.7

- [ ] **Step 7: .env を作成（トークンを設定）**

```
DISCORD_TOKEN=MTUwMjMwMDAzNTIxMDE0OTk3OQ.Gk9WEC.UsujXIMBcjUxYkhmoTOr3FAruZS4MO-1vgShRw
DB_PATH=bot.db
```

- [ ] **Step 8: コミット**

```bash
git add requirements.txt .env.example .gitignore models/schema.sql cogs/ utils/ tests/
git commit -m "feat: project scaffold"
```

---

## Task 2: バリデーションユーティリティ（TDD）

**Files:**
- Create: `utils/validators.py`
- Create: `tests/test_validators.py`

- [ ] **Step 1: テストを書く**

`tests/test_validators.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from utils.validators import parse_scheduled_time, parse_positive_int, parse_time_hhmm

JST = timezone(timedelta(hours=9))

def future_str():
    dt = datetime.now(JST) + timedelta(hours=2)
    return dt.strftime("%Y/%m/%d %H:%M")

def past_str():
    dt = datetime.now(JST) - timedelta(hours=1)
    return dt.strftime("%Y/%m/%d %H:%M")


class TestParseScheduledTime:
    def test_valid_future(self):
        dt, err = parse_scheduled_time(future_str())
        assert err is None
        assert dt is not None
        assert dt.tzinfo is not None

    def test_past_time_rejected(self):
        dt, err = parse_scheduled_time(past_str())
        assert dt is None
        assert "過去" in err

    def test_invalid_format(self):
        dt, err = parse_scheduled_time("not a date")
        assert dt is None
        assert err is not None

    def test_strips_whitespace(self):
        dt, err = parse_scheduled_time("  " + future_str() + "  ")
        assert err is None


class TestParsePositiveInt:
    def test_empty_returns_zero(self):
        n, err = parse_positive_int("", "最大人数")
        assert n == 0
        assert err is None

    def test_valid_int(self):
        n, err = parse_positive_int("5", "最大人数")
        assert n == 5
        assert err is None

    def test_negative_rejected(self):
        n, err = parse_positive_int("-1", "最大人数")
        assert n is None
        assert err is not None

    def test_non_numeric_rejected(self):
        n, err = parse_positive_int("abc", "最大人数")
        assert n is None
        assert err is not None


class TestParseTimeHhmm:
    def test_valid(self):
        v, err = parse_time_hhmm("23:00")
        assert v == "23:00"
        assert err is None

    def test_invalid(self):
        v, err = parse_time_hhmm("25:99")
        assert v is None
        assert err is not None
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
pytest tests/test_validators.py -v
```

Expected: FAILED (ImportError: cannot import name 'parse_scheduled_time')

- [ ] **Step 3: validators.py を実装**

`utils/validators.py`:
```python
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

JST = timezone(timedelta(hours=9))


def parse_scheduled_time(value: str) -> Tuple[Optional[datetime], Optional[str]]:
    try:
        dt = datetime.strptime(value.strip(), "%Y/%m/%d %H:%M").replace(tzinfo=JST)
    except ValueError:
        return None, "日時の形式が正しくありません。例: 2026/05/10 21:00"
    if dt <= datetime.now(JST):
        return None, "過去の日時は指定できません。"
    return dt, None


def parse_positive_int(value: str, field_name: str) -> Tuple[Optional[int], Optional[str]]:
    if not value.strip():
        return 0, None
    try:
        n = int(value.strip())
        if n < 0:
            raise ValueError
        return n, None
    except ValueError:
        return None, f"{field_name}は0以上の整数で入力してください。"


def parse_time_hhmm(value: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        datetime.strptime(value.strip(), "%H:%M")
        return value.strip(), None
    except ValueError:
        return None, "時刻の形式が正しくありません。例: 23:00"
```

- [ ] **Step 4: テストが通ることを確認**

```bash
pytest tests/test_validators.py -v
```

Expected: 10 passed

- [ ] **Step 5: コミット**

```bash
git add utils/validators.py tests/test_validators.py
git commit -m "feat: add input validators with tests"
```

---

## Task 3: Embed ビルダー（TDD）

**Files:**
- Create: `utils/embed_builder.py`
- Create: `tests/test_embed_builder.py`

- [ ] **Step 1: テストを書く**

`tests/test_embed_builder.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from utils.embed_builder import build_recruit_embed

JST = timezone(timedelta(hours=9))
FUTURE = datetime(2026, 5, 10, 21, 0, tzinfo=JST)


def test_title_contains_game():
    embed = build_recruit_embed(
        game="Apex Legends",
        scheduled_time=FUTURE,
        max_players=0,
        required_role_name=None,
        cancel_deadline=0,
        creator_id="123456789",
        participants=[],
    )
    assert "Apex Legends" in embed.title


def test_no_role_restriction_shows_all_ok():
    embed = build_recruit_embed("Test", FUTURE, 0, None, 0, "1", [])
    field_values = [f.value for f in embed.fields]
    assert any("全員OK" in v for v in field_values)


def test_role_restriction_shown():
    embed = build_recruit_embed("Test", FUTURE, 0, "FPSメンバー", 0, "1", [])
    field_values = [f.value for f in embed.fields]
    assert any("FPSメンバー" in v for v in field_values)


def test_max_players_shown():
    embed = build_recruit_embed("Test", FUTURE, 5, None, 0, "1", [])
    field_values = [f.value for f in embed.fields]
    assert any("5" in v for v in field_values)


def test_participants_shown():
    participants = [
        {"user_id": "111", "join_type": "confirmed", "reason": None, "available_until": None},
        {"user_id": "222", "join_type": "substitute", "reason": None, "available_until": None},
    ]
    embed = build_recruit_embed("Test", FUTURE, 0, None, 0, "1", participants)
    field_names = [f.name for f in embed.fields]
    assert any("参加" in n for n in field_names)
    assert any("補欠" in n for n in field_names)


def test_late_participant_shows_reason():
    participants = [
        {"user_id": "333", "join_type": "late", "reason": "仕事終わり次第", "available_until": None},
    ]
    embed = build_recruit_embed("Test", FUTURE, 0, None, 0, "1", participants)
    field_values = [f.value for f in embed.fields]
    assert any("仕事終わり次第" in v for v in field_values)


def test_partial_participant_shows_available_until():
    participants = [
        {"user_id": "444", "join_type": "partial", "reason": None, "available_until": "23:00"},
    ]
    embed = build_recruit_embed("Test", FUTURE, 0, None, 0, "1", participants)
    field_values = [f.value for f in embed.fields]
    assert any("23:00" in v for v in field_values)
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
pytest tests/test_embed_builder.py -v
```

Expected: FAILED (ImportError)

- [ ] **Step 3: embed_builder.py を実装**

`utils/embed_builder.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

```bash
pytest tests/test_embed_builder.py -v
```

Expected: 7 passed

- [ ] **Step 5: コミット**

```bash
git add utils/embed_builder.py tests/test_embed_builder.py
git commit -m "feat: add embed builder with tests"
```

---

## Task 4: データベース層（TDD）

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: テストを書く**

`tests/test_database.py`:
```python
import pytest
import pytest_asyncio
import aiosqlite
from database import init_db, DB_PATH
import os

# テスト用インメモリDB
TEST_DB = ":memory:"

@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(TEST_DB)
    conn.row_factory = aiosqlite.Row
    with open("models/schema.sql") as f:
        await conn.executescript(f.read())
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_insert_recruitment(db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO recruitments (guild_id, channel_id, creator_id, game, scheduled_time, "
        "max_players, cancel_deadline_minutes, status, created_at) VALUES (?,?,?,?,?,?,?,'open',?)",
        ("guild1", "ch1", "user1", "Apex", "2026-05-10T21:00:00+09:00", 5, 30, now),
    )
    await db.commit()
    async with db.execute("SELECT * FROM recruitments WHERE game = 'Apex'") as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["game"] == "Apex"
    assert row["max_players"] == 5


@pytest.mark.asyncio
async def test_participant_unique_constraint(db):
    now = "2026-01-01T00:00:00+00:00"
    await db.execute(
        "INSERT INTO recruitments (guild_id,channel_id,creator_id,game,scheduled_time,max_players,cancel_deadline_minutes,status,created_at) "
        "VALUES ('g','c','u','G',?,0,0,'open',?)", (now, now)
    )
    await db.commit()
    async with db.execute("SELECT id FROM recruitments") as cur:
        rid = (await cur.fetchone())["id"]

    await db.execute(
        "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,?,?)",
        (rid, "user1", "confirmed", now),
    )
    await db.commit()
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,?,?)",
            (rid, "user1", "confirmed", now),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_upsert_participant(db):
    now = "2026-01-01T00:00:00+00:00"
    await db.execute(
        "INSERT INTO recruitments (guild_id,channel_id,creator_id,game,scheduled_time,max_players,cancel_deadline_minutes,status,created_at) "
        "VALUES ('g','c','u','G',?,0,0,'open',?)", (now, now)
    )
    await db.commit()
    async with db.execute("SELECT id FROM recruitments") as cur:
        rid = (await cur.fetchone())["id"]

    await db.execute(
        "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,'confirmed',?) "
        "ON CONFLICT(recruitment_id,user_id) DO UPDATE SET join_type='substitute', joined_at=?",
        (rid, "user1", now, now),
    )
    await db.commit()
    await db.execute(
        "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,'confirmed',?) "
        "ON CONFLICT(recruitment_id,user_id) DO UPDATE SET join_type='substitute', joined_at=?",
        (rid, "user1", now, now),
    )
    await db.commit()
    async with db.execute("SELECT COUNT(*) as cnt FROM participants WHERE recruitment_id=?", (rid,)) as cur:
        count = (await cur.fetchone())["cnt"]
    assert count == 1
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
pytest tests/test_database.py -v
```

Expected: FAILED (ImportError: cannot import name 'init_db')

- [ ] **Step 3: database.py を実装**

`database.py`:
```python
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
```

- [ ] **Step 4: pytest.ini を作成（asyncioモード設定）**

`pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: テストが通ることを確認**

```bash
pytest tests/test_database.py -v
```

Expected: 3 passed

- [ ] **Step 6: コミット**

```bash
git add database.py tests/test_database.py pytest.ini
git commit -m "feat: add database layer with tests"
```

---

## Task 5: config.py と main.py

**Files:**
- Create: `config.py`
- Create: `main.py`

- [ ] **Step 1: config.py を作成**

`config.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN: str = os.getenv("DISCORD_TOKEN", "")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN が .env に設定されていません")
```

- [ ] **Step 2: main.py を作成**

`main.py`:
```python
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
        # Persistent Viewをリスタート後も有効化するため全open募集を再登録
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
```

- [ ] **Step 3: コミット**

```bash
git add config.py main.py
git commit -m "feat: add config and main bot entry point"
```

---

## Task 6: スケジューラー

**Files:**
- Create: `scheduler.py`

- [ ] **Step 1: scheduler.py を作成**

`scheduler.py`:
```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiosqlite
from database import DB_PATH

scheduler = AsyncIOScheduler(timezone="UTC")
NOTIFY_MINUTES = [30, 10, 5]


def start_scheduler(bot) -> None:
    scheduler.start()
    import asyncio
    asyncio.create_task(_reschedule_pending(bot))


async def _reschedule_pending(bot) -> None:
    """Bot再起動後に未送信通知を再スケジュール。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT n.recruitment_id, n.minutes_before, r.scheduled_time "
            "FROM notifications n "
            "JOIN recruitments r ON n.recruitment_id = r.id "
            "WHERE n.sent = 0 AND r.status = 'open'"
        ) as cursor:
            rows = await cursor.fetchall()

    now = datetime.now(timezone.utc)
    for row in rows:
        scheduled = datetime.fromisoformat(row["scheduled_time"])
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)

        if row["minutes_before"] == 0:
            fire_time = scheduled
            if fire_time > now:
                schedule_start_mention(bot, row["recruitment_id"], fire_time)
        else:
            fire_time = scheduled - timedelta(minutes=row["minutes_before"])
            if fire_time > now:
                schedule_notification(bot, row["recruitment_id"], row["minutes_before"], fire_time)


def schedule_notification(bot, recruitment_id: int, minutes_before: int, fire_time: datetime) -> None:
    from cogs.notifications import send_dm_notification
    job_id = f"notif_{recruitment_id}_{minutes_before}"
    scheduler.add_job(
        send_dm_notification,
        trigger="date",
        run_date=fire_time,
        args=[bot, recruitment_id, minutes_before],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,
    )


def schedule_start_mention(bot, recruitment_id: int, fire_time: datetime) -> None:
    from cogs.notifications import send_start_mention
    job_id = f"start_{recruitment_id}"
    scheduler.add_job(
        send_start_mention,
        trigger="date",
        run_date=fire_time,
        args=[bot, recruitment_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,
    )


def cancel_jobs(recruitment_id: int) -> None:
    """募集キャンセル時に関連ジョブを削除。"""
    for minutes in NOTIFY_MINUTES:
        job_id = f"notif_{recruitment_id}_{minutes}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    start_job_id = f"start_{recruitment_id}"
    if scheduler.get_job(start_job_id):
        scheduler.remove_job(start_job_id)
```

- [ ] **Step 2: コミット**

```bash
git add scheduler.py
git commit -m "feat: add APScheduler with restart recovery"
```

---

## Task 7: Notifications Cog

**Files:**
- Create: `cogs/notifications.py`

- [ ] **Step 1: notifications.py を作成**

`cogs/notifications.py`:
```python
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
            "SELECT user_id FROM participants WHERE recruitment_id = ? AND join_type IN ('confirmed','late','partial')",
            (recruitment_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        # 送信済みマーク
        await db.execute(
            "UPDATE notifications SET sent = 1 WHERE recruitment_id = ? AND minutes_before = ?",
            (recruitment_id, minutes_before),
        )
        await db.commit()

    game = recruitment["game"]
    scheduled_time = recruitment["scheduled_time"]

    for row in rows:
        try:
            user = await bot.fetch_user(int(row["user_id"]))
            await user.send(
                f"⏰ **{minutes_before}分後**に **{game}** の募集が始まります！\n"
                f"開始予定: <t:{_iso_to_timestamp(scheduled_time)}:F>"
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
            "SELECT user_id FROM participants WHERE recruitment_id = ? AND join_type IN ('confirmed','late','partial')",
            (recruitment_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        await db.execute(
            "UPDATE recruitments SET status = 'closed' WHERE id = ?", (recruitment_id,)
        )
        await db.execute(
            "UPDATE notifications SET sent = 1 WHERE recruitment_id = ? AND minutes_before = 0",
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
```

- [ ] **Step 2: コミット**

```bash
git add cogs/notifications.py
git commit -m "feat: add notifications cog with DM and mention"
```

---

## Task 8: Recruit Cog（モーダル・ボタン・コマンド）

**Files:**
- Create: `cogs/recruit.py`

- [ ] **Step 1: recruit.py を作成**

`cogs/recruit.py`:
```python
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import aiosqlite

from database import DB_PATH
from utils.validators import parse_scheduled_time, parse_positive_int, parse_time_hhmm
from utils.embed_builder import build_recruit_embed
from scheduler import schedule_notification, schedule_start_mention, cancel_jobs, NOTIFY_MINUTES

JST = timezone(timedelta(hours=9))


# ──────────────────────────────────────────────
# モーダル: 募集作成
# ──────────────────────────────────────────────

class RecruitModal(discord.ui.Modal, title="遊ぶ募集を作成"):
    game = discord.ui.TextInput(
        label="ゲーム名", placeholder="例: Apex Legends", max_length=100, required=True
    )
    scheduled_time_input = discord.ui.TextInput(
        label="開始日時 (YYYY/MM/DD HH:MM)", placeholder="例: 2026/05/10 21:00",
        max_length=16, required=True
    )
    max_players_input = discord.ui.TextInput(
        label="最大人数 (空欄=無制限)", placeholder="例: 5", max_length=3, required=False
    )
    required_role_input = discord.ui.TextInput(
        label="参加可能ロール名 (空欄=全員OK)", placeholder="例: FPSメンバー",
        max_length=100, required=False
    )
    cancel_deadline_input = discord.ui.TextInput(
        label="辞退期限 (開始X分前まで、空欄=制限なし)", placeholder="例: 30",
        max_length=4, required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # バリデーション
        scheduled_time, err = parse_scheduled_time(self.scheduled_time_input.value)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        max_players, err = parse_positive_int(self.max_players_input.value, "最大人数")
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        cancel_deadline, err = parse_positive_int(self.cancel_deadline_input.value, "辞退期限")
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        required_role_name = self.required_role_input.value.strip() or None
        if required_role_name:
            role = discord.utils.get(interaction.guild.roles, name=required_role_name)
            if not role:
                await interaction.response.send_message(
                    f"ロール「{required_role_name}」が見つかりません。サーバー内のロール名を正確に入力してください。",
                    ephemeral=True,
                )
                return

        # DB保存
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
                    str(interaction.user.id), self.game.value.strip(),
                    scheduled_iso, max_players, required_role_name, cancel_deadline, now_iso,
                ),
            )
            recruitment_id = cursor.lastrowid

            # 通知レコード（30分前/10分前/5分前 + 開始時刻）
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

        # タイマー登録
        for minutes in NOTIFY_MINUTES:
            fire_time = scheduled_time - timedelta(minutes=minutes)
            if fire_time > datetime.now(timezone.utc):
                schedule_notification(interaction.client, recruitment_id, minutes, fire_time)
        schedule_start_mention(interaction.client, recruitment_id, scheduled_time)

        # Embed投稿
        embed = build_recruit_embed(
            game=self.game.value.strip(),
            scheduled_time=scheduled_time,
            max_players=max_players,
            required_role_name=required_role_name,
            cancel_deadline=cancel_deadline,
            creator_id=str(interaction.user.id),
            participants=[],
        )
        view = RecruitView(recruitment_id)
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()

        # message_id保存
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE recruitments SET message_id = ? WHERE id = ?",
                (str(message.id), recruitment_id),
            )
            await db.commit()


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
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET join_type='late', reason=?, available_until=NULL, joined_at=?",
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
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET join_type='partial', reason=?, available_until=?, joined_at=?",
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
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET join_type='confirmed', reason=NULL, available_until=NULL, joined_at=?",
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
                "ON CONFLICT(recruitment_id, user_id) DO UPDATE SET join_type='substitute', reason=NULL, available_until=NULL, joined_at=?",
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

class RecruitView(discord.ui.View):
    def __init__(self, recruitment_id: int):
        super().__init__(timeout=None)
        self.add_item(JoinButton(recruitment_id))
        self.add_item(SubButton(recruitment_id))
        self.add_item(LateButton(recruitment_id))
        self.add_item(PartialButton(recruitment_id))
        self.add_item(CancelButton(recruitment_id))


# ──────────────────────────────────────────────
# ヘルパー関数
# ──────────────────────────────────────────────

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
        "SELECT COUNT(*) FROM participants WHERE recruitment_id = ? AND join_type IN ('confirmed','late','partial')",
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
        await interaction.response.send_modal(RecruitModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(Recruit(bot))
```

- [ ] **Step 2: コミット**

```bash
git add cogs/recruit.py
git commit -m "feat: add recruit cog with modal, buttons, and persistent view"
```

---

## Task 9: 起動テスト（ローカル）

**Files:** なし（既存ファイルの動作確認）

- [ ] **Step 1: 全テストが通ることを確認**

```bash
pytest tests/ -v
```

Expected: 全テスト PASSED

- [ ] **Step 2: Botを起動してDiscordサーバーで動作確認**

```bash
python main.py
```

Expected output:
```
[AsoBot] AsoBot#XXXX としてログインしました
[AsoBot] X サーバーに接続中
```

- [ ] **Step 3: Discordで `/recruit` コマンドが出現することを確認**

スラッシュコマンドリストに `recruit` が表示されていることを確認。
（グローバル同期は最大1時間かかる場合があるが、コマンドはすぐに表示されるはず）

- [ ] **Step 4: モーダルが開くことを確認**

`/recruit` を実行 → フォームが開く → 各フィールドに入力 → 送信 → チャンネルに募集Embedが投稿される

- [ ] **Step 5: ボタンが動作することを確認**

- ✅ 参加ボタン → Embedの参加者欄に追加される
- 🔄 補欠ボタン → 補欠欄に追加される
- ⏰ 遅れて参加 → モーダルが開く → 入力後にEmbed更新
- 🕐 途中のみ → モーダルが開く → 退出予定時刻が表示される
- ❌ 辞退 → 参加者から削除される

- [ ] **Step 6: Bot再起動後もボタンが動作することを確認**

Bot停止 → 再起動 → 既存の募集メッセージのボタンを押す → 正常動作する

---

## Task 10: CLAUDE.md と setup.sh

**Files:**
- Create: `CLAUDE.md`
- Create: `setup.sh`

- [ ] **Step 1: CLAUDE.md を作成（次回セッション用コンテキスト）**

`CLAUDE.md`:
```markdown
# AsoBot プロジェクト

## 概要
Discordで遊ぶメンバーを募集するBot。Python + discord.py 2.x。

## 技術スタック
- discord.py 2.x（スラッシュコマンド、モーダル、Persistent View）
- aiosqlite（非同期SQLite）
- APScheduler 3.x（DM通知タイマー）
- python-dotenv（.envからトークン読み込み）

## 主要ファイル
- main.py: Bot起動、Persistent View再登録、Cog読み込み
- cogs/recruit.py: /recruit コマンド、モーダル、ボタン全種
- cogs/notifications.py: DM通知・開始時メンション関数
- scheduler.py: APScheduler管理・再起動時リカバリ
- database.py: SQLite初期化
- utils/validators.py: 入力バリデーション（純粋関数）
- utils/embed_builder.py: Embed生成（純粋関数）
- models/schema.sql: DBスキーマ

## 設計上の注意
- ボタンはPersistent View（custom_id=`recruit:action:recruitment_id`）
- Bot再起動時にmain.pyのsetup_hookでopen募集のViewを全再登録する
- 日時入力はJST（UTC+9）として扱い、isoformat()でDB保存
- DM送信失敗（Forbidden）はエラーとせずログ出力のみ
- トークンは.envのみ（絶対にコードに書かない）

## デプロイ
Oracle Cloud Always Free ARM VM + systemd

## テスト
pytest tests/ -v
```

- [ ] **Step 2: setup.sh を作成**

`setup.sh`:
```bash
#!/bin/bash
set -e

echo "=== AsoBot セットアップ ==="

# Python 3.11+ 確認
python3 --version

# 仮想環境作成
python3 -m venv venv
source venv/bin/activate

# 依存インストール
pip install --upgrade pip
pip install -r requirements.txt

# .env 確認
if [ ! -f .env ]; then
    cp .env.example .env
    echo ".env を作成しました。DISCORD_TOKEN を設定してください。"
    exit 1
fi

# systemd サービス登録
BOT_DIR=$(pwd)
USER=$(whoami)

sudo tee /etc/systemd/system/aso-bot.service > /dev/null <<EOF
[Unit]
Description=AsoBot Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable aso-bot
sudo systemctl start aso-bot

echo "=== 起動完了 ==="
echo "ログ確認: journalctl -u aso-bot -f"
echo "再起動:   sudo systemctl restart aso-bot"
```

- [ ] **Step 3: 実行権限付与**

```bash
chmod +x setup.sh
```

- [ ] **Step 4: コミット**

```bash
git add CLAUDE.md setup.sh
git commit -m "docs: add CLAUDE.md and Oracle Cloud setup script"
```

---

## Task 11: 最終確認 & まとめコミット

- [ ] **Step 1: 全テスト実行**

```bash
pytest tests/ -v --tb=short
```

Expected: 全テスト PASSED

- [ ] **Step 2: ファイル構成確認**

```bash
ls -la
ls -la cogs/ utils/ tests/ models/
```

- [ ] **Step 3: .gitignore 確認（機密ファイルが除外されているか）**

```bash
git status
```

`.env` と `bot.db` が `Untracked` または `Ignored` になっていることを確認。

- [ ] **Step 4: 最終コミット**

```bash
git add -A
git status  # .env と bot.db が含まれていないことを確認してから実行
git commit -m "feat: complete AsoBot implementation"
```

---

## デプロイ手順（Oracle Cloud）

1. Oracle Cloud Always Free で ARM VM（Ubuntu 22.04）を作成
2. `git clone` でコードを転送（または `scp`）
3. `.env` を配置してトークンを設定
4. `bash setup.sh` を実行
5. `journalctl -u aso-bot -f` でログ確認
6. 更新時: `git pull && sudo systemctl restart aso-bot`
