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
