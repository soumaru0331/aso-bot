from __future__ import annotations
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiosqlite
from database import DB_PATH

scheduler = AsyncIOScheduler(timezone="UTC")
NOTIFY_MINUTES = [60, 30, 15, 10, 5]


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
            if scheduled > now:
                schedule_start_mention(bot, row["recruitment_id"], scheduled)
        else:
            fire_time = scheduled - timedelta(minutes=row["minutes_before"])
            if fire_time > now:
                schedule_notification(bot, row["recruitment_id"], row["minutes_before"], fire_time)


def schedule_notification(bot, recruitment_id: int, minutes_before: int, fire_time: datetime) -> None:
    from cogs.notifications import send_dm_notification
    scheduler.add_job(
        send_dm_notification,
        trigger="date",
        run_date=fire_time,
        args=[bot, recruitment_id, minutes_before],
        id=f"notif_{recruitment_id}_{minutes_before}",
        replace_existing=True,
        misfire_grace_time=300,
    )


def schedule_start_mention(bot, recruitment_id: int, fire_time: datetime) -> None:
    from cogs.notifications import send_start_mention
    scheduler.add_job(
        send_start_mention,
        trigger="date",
        run_date=fire_time,
        args=[bot, recruitment_id],
        id=f"start_{recruitment_id}",
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
