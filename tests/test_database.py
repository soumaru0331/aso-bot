import pytest
import pytest_asyncio
import aiosqlite
from database import init_db


@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    with open("models/schema.sql") as f:
        await conn.executescript(f.read())
    yield conn
    await conn.close()


NOW = "2026-01-01T00:00:00+00:00"
FUTURE = "2026-06-01T12:00:00+00:00"


@pytest.mark.asyncio
async def test_insert_recruitment(db):
    await db.execute(
        "INSERT INTO recruitments (guild_id, channel_id, creator_id, game, scheduled_time, "
        "max_players, cancel_deadline_minutes, status, created_at) VALUES (?,?,?,?,?,?,?,'open',?)",
        ("guild1", "ch1", "user1", "Apex", FUTURE, 5, 30, NOW),
    )
    await db.commit()
    async with db.execute("SELECT * FROM recruitments WHERE game = 'Apex'") as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["game"] == "Apex"
    assert row["max_players"] == 5


@pytest.mark.asyncio
async def test_participant_unique_constraint(db):
    await db.execute(
        "INSERT INTO recruitments (guild_id,channel_id,creator_id,game,scheduled_time,max_players,cancel_deadline_minutes,status,created_at) "
        "VALUES ('g','c','u','G',?,0,0,'open',?)", (FUTURE, NOW)
    )
    await db.commit()
    async with db.execute("SELECT id FROM recruitments") as cur:
        rid = (await cur.fetchone())["id"]

    await db.execute(
        "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,?,?)",
        (rid, "user1", "confirmed", NOW),
    )
    await db.commit()
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,?,?)",
            (rid, "user1", "confirmed", NOW),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_upsert_participant(db):
    await db.execute(
        "INSERT INTO recruitments (guild_id,channel_id,creator_id,game,scheduled_time,max_players,cancel_deadline_minutes,status,created_at) "
        "VALUES ('g','c','u','G',?,0,0,'open',?)", (FUTURE, NOW)
    )
    await db.commit()
    async with db.execute("SELECT id FROM recruitments") as cur:
        rid = (await cur.fetchone())["id"]

    for _ in range(2):
        await db.execute(
            "INSERT INTO participants (recruitment_id,user_id,join_type,joined_at) VALUES (?,?,'confirmed',?) "
            "ON CONFLICT(recruitment_id,user_id) DO UPDATE SET join_type='substitute', joined_at=?",
            (rid, "user1", NOW, NOW),
        )
        await db.commit()

    async with db.execute("SELECT COUNT(*) as cnt FROM participants WHERE recruitment_id=?", (rid,)) as cur:
        count = (await cur.fetchone())["cnt"]
    assert count == 1
