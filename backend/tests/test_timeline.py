"""
世界事件时间线测试
==================

覆盖:
- 只收录重大事件类型,过滤高频噪声(moved/observed/bit_earned…)
- 各类型格式化出可读标题
- 最新在前 + limit 夹紧 + 稳定 id
- GET /api/timeline 接口
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app
from digimon_world.world import get_world, reset_world
from digimon_world.world.timeline import (
    SIGNIFICANT_TYPES,
    TimelineSystem,
    get_timeline_system,
    reset_timeline_system,
)
from digimon_world.world.world_state import WorldState


@pytest.fixture(autouse=True)
def _reset():
    reset_world()
    reset_timeline_system()
    yield
    reset_world()
    reset_timeline_system()


def _seed_events(world: WorldState) -> None:
    """塞一批混合事件(噪声 + 重大)。"""
    world.events.extend([
        {"type": "moved", "agent": "亚古兽", "from": [0, 0], "to": [1, 1]},
        {"type": "observed", "agent": "亚古兽"},
        {"type": "bit_earned", "agent": "亚古兽", "amount": 5},
        {"type": "evolution", "description": "亚古兽 进化成了 暴龙兽", "importance": 9},
        {"type": "battle", "attacker": "亚古兽", "defender": "加布兽",
         "winner": "亚古兽", "rounds": 3},
        {"type": "disaster", "label": "暴风雪", "disaster": "blizzard"},
        {"type": "festival", "label": "满月祭", "festival": "full_moon"},
        {"type": "dialogue", "speaker": "a", "listener": "b", "line": "hi"},
        {"type": "story_event", "event_id": "dark_tower_awakening",
         "description": "黑暗塔正在苏醒……", "importance": 9},
    ])


# ---- 1. 过滤: 只留重大事件 ----


def test_filters_out_noise() -> None:
    world = WorldState()
    _seed_events(world)
    entries = TimelineSystem().build(world)

    types = {e["type"] for e in entries}
    # 噪声被滤掉
    assert "moved" not in types
    assert "observed" not in types
    assert "bit_earned" not in types
    assert "dialogue" not in types
    # 重大事件保留
    assert {"evolution", "battle", "disaster", "festival", "story_event"} <= types
    # 收录数 == 重大事件数(9 条里 5 条重大)
    assert len(entries) == 5
    for e in entries:
        assert e["type"] in SIGNIFICANT_TYPES


# ---- 2. 格式化标题 ----


def test_titles_and_icons() -> None:
    world = WorldState()
    _seed_events(world)
    by_type = {e["type"]: e for e in TimelineSystem().build(world)}

    assert by_type["evolution"]["title"] == "亚古兽 进化成了 暴龙兽"
    assert "亚古兽" in by_type["battle"]["title"]
    assert "获胜" in by_type["battle"]["title"]
    assert by_type["disaster"]["title"] == "暴风雪降临数码世界"
    assert by_type["festival"]["title"] == "满月祭举行"
    assert by_type["story_event"]["title"] == "黑暗塔正在苏醒……"

    assert by_type["evolution"]["icon"] == "✨"
    assert by_type["battle"]["icon"] == "⚔️"


def test_battle_draw_title() -> None:
    world = WorldState()
    world.events.append({"type": "battle", "attacker": "a", "defender": "b",
                         "winner": None})
    entry = TimelineSystem().build(world)[0]
    assert "平局" in entry["title"]


# ---- 3. 排序 / limit / 稳定 id ----


def test_newest_first_and_stable_id() -> None:
    world = WorldState()
    _seed_events(world)
    entries = TimelineSystem().build(world)

    # 最新在前: story_event 是最后 append 的重大事件
    assert entries[0]["type"] == "story_event"
    # id 是原始索引: story_event 在 _seed_events 里索引 8
    assert entries[0]["id"] == 8
    # 索引单调递减(倒序)
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)


def test_limit_clamped() -> None:
    world = WorldState()
    for _ in range(10):
        world.events.append({"type": "evolution", "description": "x"})

    # limit 生效
    assert len(TimelineSystem().build(world, limit=3)) == 3
    # 上限夹紧(超大 limit 不越过 MAX_LIMIT / 实际条数)
    assert len(TimelineSystem().build(world, limit=99999)) == 10
    # limit<1 兜底成 1
    assert len(TimelineSystem().build(world, limit=0)) == 1


# ---- 4. 空世界 ----


def test_empty_world() -> None:
    world = WorldState()
    payload = TimelineSystem().to_dict(world)
    assert payload["count"] == 0
    assert payload["total_events"] == 0
    assert payload["events"] == []


def test_to_dict_counts() -> None:
    world = WorldState()
    _seed_events(world)
    payload = TimelineSystem().to_dict(world)
    assert payload["count"] == 5           # 重大事件
    assert payload["total_events"] == 9    # 含噪声


# ---- 5. 单例 ----


def test_singleton() -> None:
    assert get_timeline_system() is get_timeline_system()
    reset_timeline_system()


# ---- 6. API ----


def test_api_timeline() -> None:
    client = TestClient(app)
    world = get_world()
    _seed_events(world)

    r = client.get("/api/timeline")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 5
    assert data["events"][0]["type"] == "story_event"
    assert all("icon" in e and "title" in e for e in data["events"])


def test_api_timeline_limit() -> None:
    client = TestClient(app)
    world = get_world()
    _seed_events(world)

    r = client.get("/api/timeline?limit=2")
    assert r.status_code == 200
    assert len(r.json()["events"]) == 2
