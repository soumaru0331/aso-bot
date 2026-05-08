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
