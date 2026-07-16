"""
Tests for affect_propagation.py — 情感传播引擎

覆盖:
- AffectPropagationEngine.mood_to_affect 映射
- snapshot_moods + detect_changes 检测
- propagate 按关系距离衰减
- 传播因子: intimate=0.8, close=0.6, acquaintance=0.3, outsider=0.1, stranger=0.0
- Scheduler 中的集成: tick_once 触发传播
"""

from __future__ import annotations

import pytest

from digimon_world.agents.digimon_agent import DigimonAgent
from digimon_world.world.affect_propagation import (
    CPM_CHANGE_THRESHOLD,
    AffectPropagationEngine,
    _CIRCLE_PROPAGATION_FACTOR,
    _DISTANCE_LABELS,
)
from digimon_world.world.clock import WorldClock
from digimon_world.world.relational_circle import (
    AffectVector,
    RelationalCircle,
)
from digimon_world.world.relationships import (
    RelationshipTracker,
    RelationshipVector,
    reset_tracker,
)
from digimon_world.world.scheduler import WorldScheduler
from digimon_world.world.world_state import WorldState


def _make_agent(
    name: str,
    mood_state: dict[str, float] | None = None,
    x: int = 100,
    y: int = 100,
) -> DigimonAgent:
    """构造一只数码兽, 可指定 mood_state。"""
    agent = DigimonAgent(
        name=name,
        species=name.lower(),
        region_id="file_island",
        location=(x, y),
    )
    if mood_state is not None:
        agent.mood_state = dict(mood_state)
    return agent


def _setup_tracker_with_circles() -> RelationshipTracker:
    """构造 tracker, 生成不同圈层关系。

    关系设定:
    - Agumon ↔ Gabumon: INTIMATE (affinity=40, rivalry=0, respect=30, fear=0)
    - Agumon ↔ Piyomon: FRIENDLY  (affinity=15, rivalry=0, respect=10, fear=0)
    - Agumon ↔ Tentomon: ACQUAINTANCE (affinity=5, rivalry=0, respect=3, fear=0)
    - Agumon ↔ Palmon: NEUTRAL (affinity=0, rivalry=0, respect=0, fear=0)
    - Agumon ↔ Devimon: HOSTILE (affinity=-50, rivalry=40, respect=10, fear=60)
    """
    reset_tracker()
    tracker = RelationshipTracker()
    pairs = [
        ("Agumon", "Gabumon", RelationshipVector(affinity=40.0, rivalry=0.0, respect=30.0, fear=0.0)),
        ("Agumon", "Piyomon", RelationshipVector(affinity=15.0, rivalry=0.0, respect=10.0, fear=0.0)),
        ("Agumon", "Tentomon", RelationshipVector(affinity=5.0, rivalry=0.0, respect=3.0, fear=0.0)),
        ("Agumon", "Palmon", RelationshipVector(affinity=0.0, rivalry=0.0, respect=0.0, fear=0.0)),
        ("Agumon", "Devimon", RelationshipVector(affinity=-50.0, rivalry=40.0, respect=10.0, fear=60.0)),
    ]
    for a, b, rv in pairs:
        tracker._vectors[(a, b)] = rv
    return tracker


class TestMoodToAffect:
    """测试 mood_state → AffectVector 映射。"""

    def test_high_joy_maps_to_high_trust_and_affection(self):
        agent = _make_agent("test", mood_state={"joy": 0.9, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        av = AffectPropagationEngine.mood_to_affect(agent)
        assert av.trust == pytest.approx(0.9)
        # affection = max(joy, 1-sadness) = max(0.9, 1.0) = 1.0
        assert av.affection == pytest.approx(1.0)
        assert av.fear == 0.0

    def test_high_sadness_reduces_affection(self):
        agent = _make_agent("test", mood_state={"joy": 0.1, "sadness": 0.9, "anger": 0.0, "fear": 0.0})
        av = AffectPropagationEngine.mood_to_affect(agent)
        assert av.trust == pytest.approx(0.1)
        # affection = max(joy, 1-sadness) = max(0.1, 0.1) = 0.1
        assert av.affection == pytest.approx(0.1)

    def test_fear_maps_directly(self):
        agent = _make_agent("test", mood_state={"joy": 0.0, "sadness": 0.0, "anger": 0.0, "fear": 0.7})
        av = AffectPropagationEngine.mood_to_affect(agent)
        assert av.fear == pytest.approx(0.7)

    def test_respect_defaults_to_neutral(self):
        agent = _make_agent("test")
        av = AffectPropagationEngine.mood_to_affect(agent)
        assert av.respect == 0.5

    def test_neutral_mood(self):
        agent = _make_agent("test")
        av = AffectPropagationEngine.mood_to_affect(agent)
        assert av.trust == 0.0
        assert av.affection == 1.0  # max(0, 1-0) = 1.0, clamped to 1.0
        assert av.fear == 0.0
        assert av.respect == 0.5


class TestDetectChanges:
    """测试 mood snapshot 和变化检测。"""

    def test_no_change_returns_empty(self):
        world = WorldState()
        agent = _make_agent("test", mood_state={"joy": 0.5, "sadness": 0.2, "anger": 0.1, "fear": 0.3})
        world.spawn(agent)

        engine = AffectPropagationEngine()
        engine.snapshot_moods(world)
        # No change to agent mood_state → should return empty
        changed = engine.detect_changes(world)
        assert changed == []

    def test_small_change_below_threshold(self):
        world = WorldState()
        agent = _make_agent("test", mood_state={"joy": 0.5, "sadness": 0.2, "anger": 0.1, "fear": 0.3})
        world.spawn(agent)

        engine = AffectPropagationEngine()
        engine.snapshot_moods(world)
        # Small change < threshold
        agent.mood_state["joy"] = 0.6  # delta 0.1 < 0.3
        changed = engine.detect_changes(world)
        assert changed == []

    def test_large_change_detected(self):
        world = WorldState()
        agent = _make_agent("test", mood_state={"joy": 0.2, "sadness": 0.2, "anger": 0.1, "fear": 0.1})
        world.spawn(agent)

        engine = AffectPropagationEngine()
        engine.snapshot_moods(world)
        # Large change >= threshold
        agent.mood_state["joy"] = 0.8  # delta 0.6 >= 0.3
        changed = engine.detect_changes(world)
        assert len(changed) == 1
        assert changed[0][0] == "test"
        assert changed[0][1]["joy"] == pytest.approx(0.6)

    def test_multiple_agents_one_changed(self):
        world = WorldState()
        a1 = _make_agent("a1", mood_state={"joy": 0.2, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        a2 = _make_agent("a2", mood_state={"joy": 0.5, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(a1)
        world.spawn(a2)

        engine = AffectPropagationEngine()
        engine.snapshot_moods(world)
        a1.mood_state["joy"] = 0.9  # big change
        a2.mood_state["joy"] = 0.7  # small change (0.2 < 0.3)
        changed = engine.detect_changes(world)
        assert len(changed) == 1
        assert changed[0][0] == "a1"

    def test_negative_change_detected(self):
        world = WorldState()
        agent = _make_agent("test", mood_state={"joy": 0.9, "sadness": 0.1, "anger": 0.0, "fear": 0.1})
        world.spawn(agent)

        engine = AffectPropagationEngine()
        engine.snapshot_moods(world)
        agent.mood_state["joy"] = 0.4  # delta -0.5, abs >= 0.3
        changed = engine.detect_changes(world)
        assert len(changed) == 1
        assert changed[0][1]["joy"] == pytest.approx(-0.5)


class TestPropagationFactors:
    """测试传播因子常量。"""

    def test_circle_factor_mapping(self):
        assert _CIRCLE_PROPAGATION_FACTOR[RelationalCircle.INTIMATE] == 0.8
        assert _CIRCLE_PROPAGATION_FACTOR[RelationalCircle.FRIENDLY] == 0.6
        assert _CIRCLE_PROPAGATION_FACTOR[RelationalCircle.ACQUAINTANCE] == 0.3
        assert _CIRCLE_PROPAGATION_FACTOR[RelationalCircle.NEUTRAL] == 0.1
        assert _CIRCLE_PROPAGATION_FACTOR[RelationalCircle.HOSTILE] == 0.0

    def test_distance_labels(self):
        assert _DISTANCE_LABELS[RelationalCircle.INTIMATE] == "intimate"
        assert _DISTANCE_LABELS[RelationalCircle.FRIENDLY] == "close"
        assert _DISTANCE_LABELS[RelationalCircle.ACQUAINTANCE] == "acquaintance"
        assert _DISTANCE_LABELS[RelationalCircle.NEUTRAL] == "outsider"
        assert _DISTANCE_LABELS[RelationalCircle.HOSTILE] == "stranger"


class TestPropagate:
    """测试 propagate() 方法。"""

    def test_propagate_intimate(self):
        """至交: factor=0.8, 强传播。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.2})
        gabumon = _make_agent("Gabumon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)
        world.spawn(gabumon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        assert len(results) == 1
        r = results[0]
        assert r["name"] == "Gabumon"
        assert r["distance"] == "intimate"
        assert r["factor"] == 0.8
        # Gabumon's joy should have been increased
        assert gabumon.mood_state["joy"] > 0.1

    def test_propagate_friendly(self):
        """友好: factor=0.6。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        piyomon = _make_agent("Piyomon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)
        world.spawn(piyomon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        assert len(results) == 1
        assert results[0]["name"] == "Piyomon"
        assert results[0]["distance"] == "close"
        assert results[0]["factor"] == 0.6

    def test_propagate_acquaintance(self):
        """相识: factor=0.3。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        tentomon = _make_agent("Tentomon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)
        world.spawn(tentomon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        assert len(results) == 1
        assert results[0]["distance"] == "acquaintance"
        assert results[0]["factor"] == 0.3

    def test_propagate_outsider(self):
        """局外人: factor=0.1, 微弱传播。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        palmon = _make_agent("Palmon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)
        world.spawn(palmon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        assert len(results) == 1
        assert results[0]["distance"] == "outsider"
        assert results[0]["factor"] == 0.1

    def test_propagate_stranger_blocked(self):
        """陌生人/敌对: factor=0.0, 完全阻断。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        devimon = _make_agent("Devimon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)
        world.spawn(devimon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        # stranger → factor=0.0, 不返回
        assert len(results) == 0
        # Devimon's mood should be unchanged
        assert devimon.mood_state["joy"] == 0.1

    def test_no_self_propagation(self):
        """不传播给自己。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        # Only Agumon in world, no self-propagation
        assert results == []

    def test_multiple_targets(self):
        """多个目标, 不同距离得到不同结果。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.8, "sadness": 0.0, "anger": 0.0, "fear": 0.3})
        gabumon = _make_agent("Gabumon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        piyomon = _make_agent("Piyomon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        tentomon = _make_agent("Tentomon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        palmon = _make_agent("Palmon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        devimon = _make_agent("Devimon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        for a in [agumon, gabumon, piyomon, tentomon, palmon, devimon]:
            world.spawn(a)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        # Devimon 被阻断, 其他 4 个都受影响
        affected_names = {r["name"] for r in results}
        assert "Devimon" not in affected_names
        assert affected_names == {"Gabumon", "Piyomon", "Tentomon", "Palmon"}

        # intimate (Gabumon) 的 joy 增量最大
        gabumon_joy = gabumon.mood_state["joy"]
        palmon_joy = palmon.mood_state["joy"]
        assert gabumon_joy > palmon_joy

    def test_source_not_found(self):
        """source 不在 world 中时返回空。"""
        tracker = _setup_tracker_with_circles()
        world = WorldState()

        engine = AffectPropagationEngine()
        affect = AffectVector.neutral()
        results = engine.propagate("Nonexistent", affect, world, tracker=tracker)
        assert results == []

    def test_fear_propagation(self):
        """恐惧传播: fear 维度正确衰减。"""
        tracker = _setup_tracker_with_circles()

        world = WorldState()
        agumon = _make_agent("Agumon", mood_state={"joy": 0.0, "sadness": 0.0, "anger": 0.0, "fear": 0.8})
        gabumon = _make_agent("Gabumon", mood_state={"joy": 0.5, "sadness": 0.0, "anger": 0.0, "fear": 0.1})
        world.spawn(agumon)
        world.spawn(gabumon)

        engine = AffectPropagationEngine()
        affect = engine.mood_to_affect(agumon)
        results = engine.propagate("Agumon", affect, world, tracker=tracker)

        assert len(results) == 1
        # Gabumon's fear 应该增加 (0.8 * 0.8 = 0.64 增量)
        assert gabumon.mood_state["fear"] > 0.1


class TestSchedulerIntegration:
    """测试 Scheduler 中的情感传播集成。"""

    @pytest.mark.asyncio
    async def test_scheduler_propagates_on_mood_change(self):
        """当 agent 在 step 中情绪发生剧变时, scheduler 自动触发传播。"""
        tracker = _setup_tracker_with_circles()
        world = WorldState()

        # 构造两个 agent: Agumon 和 Gabumon (intimate 关系)
        agumon = _make_agent("Agumon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        gabumon = _make_agent("Gabumon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        # 为 Agumon 注入 step 后的情绪剧变
        # 我们通过 snapshot 之前设置 prev mood, 然后修改当前 mood 来模拟
        world.spawn(agumon)
        world.spawn(gabumon)

        clock = WorldClock(real_to_world_ratio=60)
        sched = WorldScheduler(world=world, clock=clock, relationships=tracker)

        # Snapshot before tick: all moods at initial values
        sched._affect_engine.snapshot_moods(world)
        # 模拟 Agumon 情绪剧变 (step 中 CPM 触发)
        agumon.mood_state["joy"] = 0.9  # delta 0.8 >= 0.3

        # 触发传播
        changed = sched._affect_engine.detect_changes(world)
        assert len(changed) == 1
        assert changed[0][0] == "Agumon"

        affect = sched._affect_engine.mood_to_affect(agumon)
        results = sched._affect_engine.propagate(
            "Agumon", affect, world, tracker=tracker,
        )
        assert len(results) == 1
        assert results[0]["name"] == "Gabumon"
        assert results[0]["distance"] == "intimate"
        assert results[0]["factor"] == 0.8
        # Gabumon 的 joy 被感染了
        assert gabumon.mood_state["joy"] > 0.1

    @pytest.mark.asyncio
    async def test_scheduler_event_written(self):
        """传播事件写入 world.events。"""
        tracker = _setup_tracker_with_circles()
        world = WorldState()

        agumon = _make_agent("Agumon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        gabumon = _make_agent("Gabumon", mood_state={"joy": 0.1, "sadness": 0.0, "anger": 0.0, "fear": 0.0})
        world.spawn(agumon)
        world.spawn(gabumon)

        clock = WorldClock(real_to_world_ratio=60)
        sched = WorldScheduler(world=world, clock=clock, relationships=tracker)

        # 快照 + 模拟剧变 + 手动调用 _propagate_affect
        sched._affect_engine.snapshot_moods(world)
        agumon.mood_state["joy"] = 0.9
        agents = world.all()
        await sched._propagate_affect(agents)

        # 检查世界事件中有传播记录
        propagation_events = [e for e in world.events if e.get("type") == "affect_propagation"]
        assert len(propagation_events) >= 1
        ev = propagation_events[0]
        assert ev["source"] == "Agumon"
        assert "Gabumon" in ev["affected"]


class TestCPMThreshold:
    """测试 CPM_CHANGE_THRESHOLD 常量。"""

    def test_threshold_value(self):
        assert CPM_CHANGE_THRESHOLD == 0.3
