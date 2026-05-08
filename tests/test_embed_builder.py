import pytest
from datetime import datetime, timezone, timedelta
from utils.embed_builder import build_recruit_embed

JST = timezone(timedelta(hours=9))
FUTURE = datetime(2026, 5, 10, 21, 0, tzinfo=JST)


def test_title_contains_game():
    embed = build_recruit_embed("Apex Legends", FUTURE, 0, None, 0, "123456789", [])
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
