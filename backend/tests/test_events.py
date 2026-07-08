"""
剧情事件系统测试
================

覆盖:
- 剧情触发条件满足 → 事件点火并写入 world.events
- 条件不满足 → 不触发
- scheduler tick 中每 30 tick 自动 check_trigger
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent, EvolutionStage
from digimon_world.world.clock import WorldClock
from digimon_world.world.events import (
    CHECK_INTERVAL_TICKS,
    RELATIONSHIP_SUM_THRESHOLD,
    StoryDirector,
)
from digimon_world.world.relationships import RelationshipTracker
from digimon_world.world.scheduler import WorldScheduler
from digimon_world.world.world_state import WorldState


def _champion(name: str) -> DigimonAgent:
    return DigimonAgent(
        name=name,
        species="x",
        stage=EvolutionStage.CHAMPION,
        region_id="file_island",
        location=(0, 0),
    )


# ---- 1. 剧情触发条件满足 ----


def test_story_triggers_on_condition_met() -> None:
    """3+ champion → dark_tower_awakening 点火,写入 world.events。"""
    world = WorldState()
    for n in ("甲", "乙", "丙"):
        world.spawn(_champion(n))
    tracker = RelationshipTracker()

    director = StoryDirector()
    fired = director.check_trigger(world, tracker)

    fired_ids = {e.event_id for e in fired}
    assert "dark_tower_awakening" in fired_ids
    # 写进了世界事件日志
    story_events = [e for e in world.events if e.get("type") == "story_event"]
    assert any(e["event_id"] == "dark_tower_awakening" for e in story_events)

    # 再扫一次不重复触发(fired 标记)
    again = director.check_trigger(world, tracker)
    assert all(e.event_id != "dark_tower_awakening" for e in again)


def test_creators_return_on_relationship_sum() -> None:
    """关系总和 > 200 → creators_return 点火。"""
    world = WorldState()
    tracker = RelationshipTracker()
    # 关系总和超阈值
    tracker.update("a", "b", 100)
    tracker.update("c", "d", 100)
    tracker.update("e", "f", 50)
    assert sum(p["score"] for p in tracker.all_pairs()) > RELATIONSHIP_SUM_THRESHOLD

    director = StoryDirector()
    fired = director.check_trigger(world, tracker)
    assert "creators_return" in {e.event_id for e in fired}


# ---- 2. 条件不满足不触发 ----


def test_no_trigger_when_condition_unmet() -> None:
    """空世界 + 空关系 → 无事件点火。"""
    world = WorldState()
    tracker = RelationshipTracker()

    director = StoryDirector()
    fired = director.check_trigger(world, tracker)
    assert fired == []
    assert not [e for e in world.events if e.get("type") == "story_event"]


# ---- 3. scheduler tick 中自动触发 ----


@pytest.mark.asyncio
async def test_scheduler_auto_checks_trigger() -> None:
    """tick 每 CHECK_INTERVAL_TICKS 扫描一次;满足条件的剧情自动点火。"""
    world = WorldState()
    for n in ("甲", "乙", "丙"):
        world.spawn(_champion(n))
    tracker = RelationshipTracker()
    director = StoryDirector()
    clock = WorldClock()

    sched = WorldScheduler(
        world=world,
        clock=clock,
        relationships=tracker,
        story_director=director,
    )

    # 第一个 tick (tick_count == 0) 即扫描 → dark_tower 点火
    await sched.tick_once()
    assert any(
        e.get("event_id") == "dark_tower_awakening"
        for e in world.events
        if e.get("type") == "story_event"
    )
    # 确认扫描间隔常量存在(供 scheduler 引用)
    assert CHECK_INTERVAL_TICKS == 30
