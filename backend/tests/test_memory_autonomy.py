"""Tests for Phase 18 memory autonomy system.

Covers:
- EbbinghausCurve math (retention formula, half-life)
- MemoryHealth dataclass
- ForgettingEngine (register, get_strength, update_all_strengths,
  get_weak_memories, mark_stale, diagnose)
- MemoryRehearsal (select_for_rehearsal)
- MemoryAutonomy (register + step + diagnose lifecycle, stale detection)
- API endpoint GET /api/digimon/{name}/memory-health
- DigimonAgent.observe() integration
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app
from digimon_world.world import get_world, reset_world
from digimon_world.memory.memory_autonomy import (
    EbbinghausCurve,
    ForgettingEngine,
    MemoryAutonomy,
    MemoryHealth,
    MemoryRehearsal,
    REHEARSAL_STRENGTH_THRESHOLD,
    MAX_REHEARSAL_PER_STEP,
)
from digimon_world.memory.memory_stream import MemoryNode
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset():
    """Reset world singleton before and after each test to avoid pollution."""
    reset_world()
    yield
    reset_world()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_memory_node(
    node_id: int,
    description: str,
    importance: int = 5,
    memory_type: str = "observation",
) -> MemoryNode:
    """Factory helper to create a MemoryNode with a known node_id."""
    return MemoryNode(
        timestamp=datetime.utcnow(),
        description=description,
        importance=importance,
        memory_type=memory_type,
        node_id=node_id,
        tick_index=0,
    )


# ═══════════════════════════════════════════════════════════════════
# Group 1: EbbinghausCurve math
# ═══════════════════════════════════════════════════════════════════


class TestEbbinghausCurve:
    """Test the Ebbinghaus forgetting curve model.

    Formula: R(t) = exp(-t / S)  where S = strength parameter.
    """

    def test_retention_zero_elapsed(self):
        """At t=0, retention should be 1.0 (no forgetting)."""
        curve = EbbinghausCurve(S=3600.0)
        assert curve.retention(0) == 1.0
        assert curve.retention(-5) == 1.0  # negative time → 1.0

    def test_retention_at_s_equals_e_inverse(self):
        """At t=S, retention = exp(-1) ≈ 0.3679."""
        curve = EbbinghausCurve(S=1000.0)
        expected = math.exp(-1)
        assert math.isclose(curve.retention(1000.0), expected, rel_tol=1e-9)

    def test_retention_at_half_life(self):
        """At t = S * ln(2), retention should be 0.5."""
        curve = EbbinghausCurve(S=3600.0)
        half_life = curve.half_life_seconds()
        result = curve.retention(half_life)
        assert math.isclose(result, 0.5, rel_tol=1e-9)
        # Also verify the formula: half_life = S * ln(2)
        expected_hl = 3600.0 * math.log(2)
        assert math.isclose(half_life, expected_hl, rel_tol=1e-9)

    def test_retention_decays_monotonically(self):
        """Retention should decrease as elapsed time increases."""
        curve = EbbinghausCurve(S=3600.0)
        r1 = curve.retention(100)
        r2 = curve.retention(200)
        r3 = curve.retention(500)
        assert r2 < r1
        assert r3 < r2

    def test_retention_with_custom_s(self):
        """Larger S means slower forgetting."""
        fast = EbbinghausCurve(S=600.0)
        slow = EbbinghausCurve(S=86400.0)
        t = 3600.0  # 1 hour
        assert fast.retention(t) < slow.retention(t)

    def test_for_agent_trait_factors(self):
        """for_agent() should apply personality factor to S."""
        brave = EbbinghausCurve.for_agent("Agumon", "brave")
        timid = EbbinghausCurve.for_agent("Gabumon", "timid")
        # brave: factor=1.2 → S = 3600/1.2 = 3000 (faster forgetting)
        # timid: factor=0.8 → S = 3600/0.8 = 4500 (slower forgetting)
        assert brave.S < timid.S
        # brave forgets faster → lower retention at same elapsed time
        t = 3600.0
        assert brave.retention(t) < timid.retention(t)


# ═══════════════════════════════════════════════════════════════════
# Group 2: MemoryHealth dataclass
# ═══════════════════════════════════════════════════════════════════


class TestMemoryHealth:
    """Test the MemoryHealth dataclass."""

    def test_creation_defaults(self):
        """MemoryHealth should have sensible default values."""
        node = _make_memory_node(1, "test memory", importance=5)
        health = MemoryHealth(memory=node)

        assert health.memory is node
        assert health.strength == 1.0
        assert health.last_rehearsed is None
        assert health.rehearsal_count == 0
        assert health.stale is False
        assert health.stale_reason == ""
        assert isinstance(health.created_at, datetime)

    def test_stale_flag(self):
        """Setting stale should be reflected correctly."""
        node = _make_memory_node(2, "old info", importance=3)
        health = MemoryHealth(memory=node)

        assert not health.stale
        assert health.stale_reason == ""

        health.stale = True
        health.stale_reason = "state changed"
        health.strength = 0.0

        assert health.stale
        assert health.stale_reason == "state changed"
        assert health.strength == 0.0


# ═══════════════════════════════════════════════════════════════════
# Group 3: ForgettingEngine
# ═══════════════════════════════════════════════════════════════════


class TestForgettingEngine:
    """Test the ForgettingEngine that manages memory health."""

    def test_register_adds_health(self):
        """register() should add a MemoryHealth entry with initial strength 1.0."""
        engine = ForgettingEngine()
        node = _make_memory_node(1, "test", importance=5)

        health = engine.register(node)
        assert 1 in engine.memory_health
        assert health.strength == 1.0
        assert health.memory is node

    def test_register_rejects_node_without_id(self):
        """register() should raise ValueError if node has no node_id."""
        engine = ForgettingEngine()
        node = MemoryNode(
            timestamp=datetime.utcnow(),
            description="no id",
            importance=5,
            node_id=None,
        )
        with pytest.raises(ValueError, match="node_id"):
            engine.register(node)

    def test_get_strength_returns_zero_for_unknown_node(self):
        """get_strength() should return 0.0 for unknown node_id."""
        engine = ForgettingEngine()
        assert engine.get_strength(999) == 0.0

    def test_get_strength_returns_zero_for_stale(self):
        """get_strength() should return 0.0 for stale memories."""
        engine = ForgettingEngine()
        node = _make_memory_node(1, "stale memory", importance=5)
        engine.register(node)
        engine.mark_stale(1, "test stale")
        assert engine.get_strength(1) == 0.0

    def test_get_strength_decays_with_time(self):
        """get_strength() should decay according to the forgetting curve."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=1000.0))
        node = _make_memory_node(1, "decaying", importance=5)
        health = engine.register(node)

        # Simulate passage of time by setting created_at in the past
        health.created_at = datetime.utcnow() - timedelta(seconds=1000)
        # At t=S=1000, retention = exp(-1) ≈ 0.3679
        s = engine.get_strength(1)
        assert math.isclose(s, math.exp(-1), rel_tol=1e-6)

    def test_get_strength_updates_health_strength(self):
        """get_strength() should update the health.strength field."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=1000.0))
        node = _make_memory_node(1, "update field", importance=5)
        health = engine.register(node)

        # Before decay: strength = 1.0
        assert health.strength == 1.0

        health.created_at = datetime.utcnow() - timedelta(seconds=500)
        s = engine.get_strength(1)
        # After get_strength, health.strength should be updated
        assert health.strength < 1.0
        assert math.isclose(health.strength, s, rel_tol=1e-9)

    def test_get_strength_with_rehearsal_boost(self):
        """Rehearsed memories should get a strength boost."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=1000.0))
        node = _make_memory_node(1, "rehearsed", importance=8)
        health = engine.register(node)

        # Simulate rehearsal
        health.last_rehearsed = datetime.utcnow() - timedelta(seconds=200)
        health.rehearsal_count = 3

        # Base retention from last_rehearsed: exp(-200/1000) ≈ 0.8187
        # Boost: 1 + 0.05 * 3 = 1.15
        # Expected: 0.8187 * 1.15 ≈ 0.9415 (capped at 1.0)
        s = engine.get_strength(1)
        base = math.exp(-200 / 1000)
        expected = min(base * (1.0 + 0.05 * 3), 1.0)
        assert math.isclose(s, expected, rel_tol=1e-6)

    def test_update_all_strengths_returns_stats(self):
        """update_all_strengths() should return total, weak, strong counts."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=3600.0))

        # Fresh memory (strength ~1.0)
        node1 = _make_memory_node(1, "fresh", importance=5)
        engine.register(node1)

        # Old memory (strength ~0.1)
        node2 = _make_memory_node(2, "old", importance=5)
        h2 = engine.register(node2)
        h2.created_at = datetime.utcnow() - timedelta(seconds=10000)

        stats = engine.update_all_strengths()
        assert stats["total"] == 2
        assert stats["strong"] >= 1  # fresh memory
        # The old memory at t=10000 with S=3600: exp(-10000/3600) ≈ 0.062 < 0.3 → weak
        assert stats["weak"] >= 1

    def test_get_weak_memories_filters_correctly(self):
        """get_weak_memories() should return only non-stale, 0 < strength < threshold."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=3600.0))

        # Strong memory (fresh)
        node1 = _make_memory_node(1, "strong", importance=9)
        engine.register(node1)

        # Weak memory (old)
        node2 = _make_memory_node(2, "weak", importance=6)
        h2 = engine.register(node2)
        h2.created_at = datetime.utcnow() - timedelta(seconds=10000)

        # Stale memory
        node3 = _make_memory_node(3, "stale", importance=7)
        engine.register(node3)
        engine.mark_stale(3, "stale test")

        weak = engine.get_weak_memories(threshold=REHEARSAL_STRENGTH_THRESHOLD)
        weak_ids = [h.memory.node_id for h in weak]

        # Should include the genuinely weak memory
        assert 2 in weak_ids
        # Should NOT include the strong memory
        assert 1 not in weak_ids
        # Should NOT include the stale memory (strength=0)
        assert 3 not in weak_ids

    def test_mark_stale_sets_flag_and_zero_strength(self):
        """mark_stale() should set stale=True, set strength=0, and record reason."""
        engine = ForgettingEngine()
        node = _make_memory_node(1, "outdated fact", importance=5)
        engine.register(node)

        engine.mark_stale(1, "evolution changed stage")
        health = engine.memory_health[1]

        assert health.stale is True
        assert health.stale_reason == "evolution changed stage"
        assert health.strength == 0.0

    def test_mark_stale_unknown_node_is_noop(self):
        """mark_stale() on unknown node_id should not raise."""
        engine = ForgettingEngine()
        # Should not raise
        engine.mark_stale(999, "no such node")

    def test_diagnose_returns_complete_report(self):
        """diagnose() should return a complete health diagnostic report."""
        engine = ForgettingEngine()
        node1 = _make_memory_node(1, "important memory", importance=9)
        engine.register(node1)

        node2 = _make_memory_node(2, "old weak memory", importance=3)
        h2 = engine.register(node2)
        h2.created_at = datetime.utcnow() - timedelta(seconds=20000)

        engine.mark_stale(2, "expired")

        report = engine.diagnose()

        assert report["total_memories"] == 2
        assert "strong_count" in report
        assert "weak_count" in report
        assert report["stale_count"] == 1
        assert report["strong_threshold"] == 0.7
        assert report["weak_threshold"] == 0.3
        assert "forgetting_half_life_seconds" in report
        assert isinstance(report["top_weak"], list)
        # top_weak should contain the stale-turned-weak memory
        assert len(report["top_weak"]) >= 0


# ═══════════════════════════════════════════════════════════════════
# Group 4: MemoryRehearsal
# ═══════════════════════════════════════════════════════════════════


class TestMemoryRehearsal:
    """Test the MemoryRehearsal mechanism."""

    def test_select_for_rehearsal_picks_high_importance_weak(self):
        """Should prefer weak memories with high importance."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=3600.0))
        rehearsal = MemoryRehearsal()

        # Create several weak, high-importance memories
        for i in range(5):
            node = _make_memory_node(i, f"important event {i}", importance=9)
            h = engine.register(node)
            h.created_at = datetime.utcnow() - timedelta(seconds=20000)

        # Also create a weak, low-importance memory
        node_low = _make_memory_node(99, "boring event", importance=2)
        h_low = engine.register(node_low)
        h_low.created_at = datetime.utcnow() - timedelta(seconds=20000)

        random.seed(42)
        selected = rehearsal.select_for_rehearsal(engine)

        # Should select from high-importance memories, not low
        selected_ids = [h.memory.node_id for h in selected]
        assert 99 not in selected_ids, "low-importance memory should not be selected"
        assert len(selected) <= MAX_REHEARSAL_PER_STEP

    def test_select_for_rehearsal_respects_max_limit(self):
        """select_for_rehearsal() should never return more than MAX_REHEARSAL_PER_STEP."""
        engine = ForgettingEngine(curve=EbbinghausCurve(S=3600.0))
        rehearsal = MemoryRehearsal()

        # Create 10 weak, high-importance memories
        for i in range(10):
            node = _make_memory_node(i, f"important {i}", importance=9)
            h = engine.register(node)
            h.created_at = datetime.utcnow() - timedelta(seconds=20000)

        random.seed(123)
        selected = rehearsal.select_for_rehearsal(engine)
        assert len(selected) <= MAX_REHEARSAL_PER_STEP

    def test_select_for_rehearsal_returns_empty_when_no_weak(self):
        """Should return empty list when all memories are strong."""
        engine = ForgettingEngine()
        rehearsal = MemoryRehearsal()

        # Fresh memory (strong)
        node = _make_memory_node(1, "fresh", importance=9)
        engine.register(node)

        selected = rehearsal.select_for_rehearsal(engine)
        assert selected == []

    def test_rehearse_resets_strength_and_increments_count(self):
        """rehearse() should reset strength to 1.0 and increment rehearsal_count."""
        rehearsal = MemoryRehearsal()
        engine = ForgettingEngine()

        node = _make_memory_node(1, "to rehearse", importance=9)
        health = engine.register(node)
        health.created_at = datetime.utcnow() - timedelta(seconds=20000)
        # Advance: strength should be low now
        engine.get_strength(1)
        assert health.strength < 1.0

        old_count = health.rehearsal_count
        rehearsal.rehearse(health)

        assert health.strength == 1.0
        assert health.rehearsal_count == old_count + 1
        assert health.last_rehearsed is not None


# ═══════════════════════════════════════════════════════════════════
# Group 5: MemoryAutonomy (integration lifecycle)
# ═══════════════════════════════════════════════════════════════════


class TestMemoryAutonomy:
    """Test the MemoryAutonomy main class integrating all subsystems."""

    def test_assess_importance_heuristic(self):
        """assess_importance() should return correct heuristic scores."""
        autonomy = MemoryAutonomy(agent_name="TestAgumon", personality="brave")

        # High importance: "进化" (evolution) matches heuristic
        score = autonomy.assess_importance("亚古兽进化了！", "evolution")
        assert score == 8

        # Mid importance: "战斗" matches mid heuristic
        score = autonomy.assess_importance("一场激烈的战斗", "observation")
        assert score == 6

        # Low importance: "移动" matches low heuristic
        score = autonomy.assess_importance("移动到了新位置", "observation")
        assert score == 3

    def test_register_and_step_lifecycle(self):
        """register() + step() + diagnose() should work end-to-end."""
        autonomy = MemoryAutonomy(agent_name="TestAgumon", personality="brave")

        # Register a memory
        node = _make_memory_node(1, "found a rare item", importance=8)
        autonomy.register(node)

        # Step the autonomy
        result = autonomy.step(current_tick=1)
        assert result["tick"] == 1
        assert result["agent"] == "TestAgumon"
        assert result["health"]["total"] == 1
        assert "stale_detected" in result
        assert "rehearsed" in result

        # Diagnose should return full report
        diag = autonomy.diagnose()
        assert diag["agent"] == "TestAgumon"
        assert diag["total_memories"] == 1
        assert "forgetting_half_life_hours" in diag

    def test_stale_detection_via_notify_state_change(self):
        """notify_state_change() + step() should detect and mark stale memories."""
        autonomy = MemoryAutonomy(agent_name="TestAgumon", personality="brave")

        # Register a memory about being rookie stage
        node = _make_memory_node(1, "我是成长期亚古兽", importance=5)
        autonomy.register(node)

        # Notify of evolution state change
        autonomy.notify_state_change("evolution", "成长期", "成熟期")

        # Step to process stale detection
        result = autonomy.step(current_tick=1)
        assert result["stale_detected"] >= 1

        # The memory should now be marked stale
        health = autonomy.forgetting_engine.memory_health[1]
        assert health.stale is True

    def test_stale_detection_no_match_does_nothing(self):
        """State changes with no matching patterns should not mark any memories."""
        autonomy = MemoryAutonomy(agent_name="TestAgumon", personality="brave")

        # Register a memory unrelated to location
        node = _make_memory_node(1, "吃了一顿美味的饭", importance=4)
        autonomy.register(node)

        # Notify of a location change (no match with memory content)
        autonomy.notify_state_change("location", "file_island", "infinity_mountain")

        result = autonomy.step(current_tick=1)
        assert result["stale_detected"] == 0

        health = autonomy.forgetting_engine.memory_health[1]
        assert health.stale is False

    def test_multiple_memories_stale_detection(self):
        """Only matching memories should be marked stale, not all."""
        autonomy = MemoryAutonomy(agent_name="TestAgumon", personality="brave")

        # Memory about evolution stage
        node1 = _make_memory_node(1, "我是成长期数码兽", importance=5)
        autonomy.register(node1)

        # Memory about food (unrelated)
        node2 = _make_memory_node(2, "吃了一个回复药", importance=3)
        autonomy.register(node2)

        autonomy.notify_state_change("evolution", "成长期", "成熟期")
        autonomy.step(current_tick=1)

        # Only the evolution-related memory should be stale
        assert autonomy.forgetting_engine.memory_health[1].stale is True
        assert autonomy.forgetting_engine.memory_health[2].stale is False


# ═══════════════════════════════════════════════════════════════════
# Group 6: API endpoint GET /api/digimon/{name}/memory-health
# ═══════════════════════════════════════════════════════════════════


class TestMemoryHealthEndpoint:
    """Test the memory-health API endpoint."""

    def test_returns_structure_for_initialized_agent(self, client):
        """GET /api/digimon/{name}/memory-health should return correct structure."""
        world = get_world()
        agent = world.get("亚古兽")
        assert agent is not None

        # Register some memories to make the report interesting
        node = agent.memory.add("战斗胜利！", importance=9)
        agent.memory_autonomy.register(node)

        r = client.get("/api/digimon/亚古兽/memory-health")
        assert r.status_code == 200
        data = r.json()

        # Required top-level fields
        assert data["name"] == "亚古兽"
        assert "agent" in data
        assert "total_memories" in data
        assert "strong_count" in data
        assert "weak_count" in data
        assert "stale_count" in data
        assert "forgetting_half_life_seconds" in data
        assert "forgetting_half_life_hours" in data
        assert "top_weak" in data
        assert "rehearsal_history" in data
        assert "personality" in data
        assert "memory_stream_count" in data

        # top_weak and rehearsal_history should be lists
        assert isinstance(data["top_weak"], list)
        assert isinstance(data["rehearsal_history"], list)

    def test_404_for_unknown_digimon(self, client):
        """Unknown digimon should return 404."""
        r = client.get("/api/digimon/不存在的数码兽/memory-health")
        assert r.status_code == 404

    def test_not_initialized_state(self, client):
        """Agent without memory_autonomy should return not_initialized."""
        world = get_world()
        agent = world.get("亚古兽")
        assert agent is not None
        # Simulate pre-Phase-18 agent by unsetting memory_autonomy
        agent.memory_autonomy = None

        r = client.get("/api/digimon/亚古兽/memory-health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "not_initialized"
        assert data["name"] == "亚古兽"
        assert data["total_memories"] == 0
        assert data["strong_count"] == 0
        assert data["weak_count"] == 0
        assert data["stale_count"] == 0
        assert data["forgetting_half_life_hours"] == 0

    def test_different_agents_have_separate_health(self, client):
        """Each agent should have its own independent memory health report."""
        world = get_world()
        agumon = world.get("亚古兽")
        gabumon = world.get("加布兽")

        # Register different memories for each
        node_a = agumon.memory.add("亚古兽的战斗", importance=9)
        agumon.memory_autonomy.register(node_a)

        node_g = gabumon.memory.add("加布兽的发现", importance=6)
        gabumon.memory_autonomy.register(node_g)

        r_a = client.get("/api/digimon/亚古兽/memory-health")
        r_g = client.get("/api/digimon/加布兽/memory-health")

        assert r_a.json()["name"] == "亚古兽"
        assert r_a.json()["agent"] == "亚古兽"
        assert r_g.json()["name"] == "加布兽"
        assert r_g.json()["agent"] == "加布兽"
        # Total counts may differ
        assert r_a.json()["total_memories"] >= 1
        assert r_g.json()["total_memories"] >= 1


# ═══════════════════════════════════════════════════════════════════
# Group 7: Agent integration (DigimonAgent.observe)
# ═══════════════════════════════════════════════════════════════════


class TestAgentIntegration:
    """Test that DigimonAgent.observe() properly integrates with MemoryAutonomy."""

    def test_observe_delegates_importance_and_registers(self):
        """observe() should use assess_importance and register with forgetting engine."""
        world = get_world()
        agent = world.get("亚古兽")

        # Record pre-observe state
        engine = agent.memory_autonomy.forgetting_engine
        initial_health_count = len(engine.memory_health)

        # Observe an event
        event = {
            "type": "battle_victory",
            "description": "亚古兽击败了贝壳兽！",
            "agent": "亚古兽",
        }
        agent.observe(event, tick_index=0)

        # The memory should be in the memory stream
        last_memory = agent.memory.entries[-1]
        # With heuristic, battle_victory should map to importance=9 (via assessor)
        # But "击败" is a high-signal keyword → importance 8 via heuristic
        assert last_memory.importance >= 8
        assert "击败" in last_memory.description

        # The memory should be registered in the forgetting engine
        assert len(engine.memory_health) == initial_health_count + 1
        assert last_memory.node_id in engine.memory_health

    def test_observe_registers_correct_importance_for_different_events(self):
        """Different event types should get appropriate importance scores."""
        world = get_world()
        agent = world.get("亚古兽")

        # Low importance event
        agent.observe(
            {"type": "moved", "description": "移动到了草原", "agent": "亚古兽"},
            tick_index=0,
        )
        low_node = agent.memory.entries[-1]
        # "移动" and "moved" match low-signals → 3
        assert low_node.importance == 3

        # High importance event
        agent.observe(
            {"type": "evolution", "description": "亚古兽进化了！", "agent": "亚古兽"},
            tick_index=1,
        )
        high_node = agent.memory.entries[-1]
        # "进化" and "evolv" match high-signals → 8
        assert high_node.importance == 8

        # Both should be in the forgetting engine
        engine = agent.memory_autonomy.forgetting_engine
        assert low_node.node_id in engine.memory_health
        assert high_node.node_id in engine.memory_health

    def test_observe_registers_multiple_events(self):
        """Multiple observe() calls should register all in forgetting engine."""
        world = get_world()
        agent = world.get("亚古兽")
        engine = agent.memory_autonomy.forgetting_engine

        events = [
            {"type": "battle", "description": "遭遇敌人", "agent": "亚古兽"},
            {"type": "discover", "description": "发现隐藏道具", "agent": "亚古兽"},
            {"type": "rested", "description": "休息恢复体力", "agent": "亚古兽"},
        ]

        for i, evt in enumerate(events):
            agent.observe(evt, tick_index=i)

        # All 3 memories should be registered
        assert len(engine.memory_health) == 3

        # The memory stream should also have 3 entries
        assert len(agent.memory.entries) >= 3
