"""Phase 14: 世界叙事系统测试。

测试 NarratorSystem 单例、事件收集、LLM 叙事生成、API 端点。
"""
from __future__ import annotations


def test_narrator_singleton():
    """验证 NarratorSystem 单例模式。"""
    from digimon_world.world.narrator import get_narrator, NarratorSystem

    n1 = get_narrator()
    n2 = get_narrator()
    assert n1 is n2
    assert isinstance(n1, NarratorSystem)
    assert n1.journal == []
    assert n1.narration_interval == 100
    assert n1._tick_counter == 0
    assert n1._last_narrated_at == 0


def test_narrator_tick_skips_when_not_interval():
    """验证 tick 在未到间隔时不采集事件。"""
    from digimon_world.world.narrator import get_narrator, NarratorSystem
    from digimon_world.world import reset_narrator

    reset_narrator()
    n = get_narrator()
    # 前 99 tick 应该跳过
    for _ in range(99):
        n.tick(world=None, timeline_system=None)
    assert n._tick_counter == 99
    assert n.journal == []
    # 第 100 tick 触发
    n.tick(world=None, timeline_system=None)
    assert n._tick_counter == 100
    # 没有 world 时应该不会崩溃,也不会添加叙事


def test_narrator_interval_custom():
    """验证可自定义叙事间隔。"""
    from digimon_world.world.narrator import NarratorSystem

    n = NarratorSystem(interval=50)
    assert n.narration_interval == 50


def test_reset_narrator():
    """验证 reset 函数。"""
    from digimon_world.world.narrator import (
        get_narrator,
        reset_narrator,
    )

    n1 = get_narrator()
    assert n1 is not None
    reset_narrator()
    n2 = get_narrator()
    assert n2 is not None
    assert n1 is not n2


def test_collect_context_basic():
    """验证 _collect_context 统计各类型事件。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator
    from digimon_world.world.world_state import get_world, reset_world

    reset_world()
    reset_narrator()
    n = NarratorSystem()
    world = get_world()

    # 构造时间线条目 (模拟 TimelineSystem.build 的输出格式)
    timeline_entries = [
        {"type": "evolution", "icon": "✨", "title": "亚古兽进化暴龙兽", "importance": 9},
        {"type": "battle", "icon": "⚔️", "title": "暴龙兽 vs 恶魔兽", "importance": 8},
        {"type": "battle", "icon": "⚔️", "title": "加布兽 vs 邪龙兽", "importance": 7},
        {"type": "story_event", "icon": "📜", "title": "黑暗齿轮出现", "importance": 8},
        {"type": "first_meet", "icon": "🤝", "title": "巴鲁兽遇到哥玛兽", "importance": 5},
        {"type": "disaster", "icon": "🌋", "title": "火山爆发", "importance": 9},
    ]

    ctx = n._collect_context(world, timeline_entries)
    assert "events" in ctx
    assert ctx["evolution_count"] == 1
    assert ctx["battle_count"] == 2
    assert len(ctx["story_events"]) == 1
    assert len(ctx["first_meets"]) == 1
    assert ctx["disaster_count"] == 1
    assert ctx["agent_count"] == world.count()
    assert ctx["tick"] == n._tick_counter
    # 验证按重要性排序: 最高 importance 的事件应该在前
    assert ctx["events"][0]["importance"] >= ctx["events"][-1]["importance"]


def test_collect_context_empty():
    """验证空事件列表不崩溃。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator
    from digimon_world.world.world_state import get_world, reset_world

    reset_world()
    reset_narrator()
    n = NarratorSystem()
    world = get_world()

    ctx = n._collect_context(world, [])
    assert ctx["events"] == []
    assert ctx["evolution_count"] == 0
    assert ctx["battle_count"] == 0
    assert ctx["disaster_count"] == 0
    assert ctx["story_events"] == []
    assert ctx["first_meets"] == []


def test_compose_sync():
    """验证 _compose (同步版本) 返回正确的结构。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    reset_narrator()
    n = NarratorSystem()
    n._tick_counter = 100
    context = {
        "tick": 100,
        "agent_count": 30,
        "events": [],
        "evolution_count": 1,
        "battle_count": 2,
        "disaster_count": 0,
    }
    result = n._compose(context)
    assert "story" in result
    assert "title" in result
    assert "events_count" in result
    assert result["evolution_count"] == 1
    assert result["battle_count"] == 2
    assert result["tick"] == 100
    assert isinstance(result["story"], str)
    assert len(result["story"]) > 0


def test_narration_count_property():
    """验证 narration_count 属性。"""
    from digimon_world.world.narrator import NarratorSystem, reset_narrator

    reset_narrator()
    n = NarratorSystem()
    assert n.narration_count == 0
    n.journal.append({"tick": 100, "title": "test", "story": "test"})
    assert n.narration_count == 1
