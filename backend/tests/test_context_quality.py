"""
Phase 25 Task 1 — context_quality.py 集成测试
=============================================

测试 ContextQualitySnapshot, ContextHealthMonitor, ContextOptimizer.
适配 subagent 的详细实现（阈值常量、私有辅助方法、_plan_engine 等）。
"""

from __future__ import annotations

from digimon_world.world.context_quality import (
    ContextQualitySnapshot,
    ContextHealthMonitor,
    ContextOptimizer,
    ContextIssue,
)


# ---------------------------------------------------------------------------
# ContextQualitySnapshot
# ---------------------------------------------------------------------------

class TestContextQualitySnapshot:
    """测试快照数据类。"""

    def test_default_snapshot(self) -> None:
        s = ContextQualitySnapshot(agent_name="agumon", tick=0)
        assert s.agent_name == "agumon"
        assert s.tick == 0
        assert s.memory_count == 0
        assert s.memory_staleness == 0.0

    def test_full_snapshot_fields(self) -> None:
        s = ContextQualitySnapshot(
            agent_name="gabumon", tick=42, memory_count=15,
            memory_staleness=0.3, memory_relevance=0.8, plan_currency=0.9,
            world_model_coverage=0.5, context_size_estimate=3500,
            coherence_score=0.73, composite_health=72.5,
        )
        assert s.composite_health == 72.5

    def test_snapshot_has_timestamp(self) -> None:
        s = ContextQualitySnapshot(agent_name="test", tick=0)
        assert hasattr(s, "timestamp")
        assert s.timestamp  # auto-generated


# ---------------------------------------------------------------------------
# ContextHealthMonitor — diagnose (subagent thresholds)
# ---------------------------------------------------------------------------

# Subagent thresholds (from context_quality.py constants):
# STALENESS_WARNING=0.5, STALENESS_CRITICAL=0.7
# RELEVANCE_WARNING=0.4, RELEVANCE_CRITICAL=0.2
# PLAN_CURRENCY_WARNING=0.4, PLAN_CURRENCY_CRITICAL=0.2
# COHERENCE_WARNING=0.5, COHERENCE_CRITICAL=0.3

class TestContextHealthDiagnose:
    """测试问题诊断逻辑。"""

    def test_empty_snapshot_produces_issues(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(agent_name="x", tick=0)
        issues = monitor.diagnose(snap)
        # With all zeros: coherence <= 0.3 → critical, plan_currency <= 0.2 → critical
        # relevance <= 0.2 → critical (or size=0 doesn't trigger overload)
        assert len(issues) >= 2

    def test_healthy_snapshot_no_issues(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="healthy", tick=10, memory_count=20,
            memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.9,
            world_model_coverage=0.6, context_size_estimate=4000,
            coherence_score=0.77, composite_health=78.0,
        )
        issues = monitor.diagnose(snap)
        assert len(issues) == 0

    def test_staleness_warning(self) -> None:
        """staleness >= 0.7 is warning, >= 0.9 is critical."""
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="stale", tick=100, memory_count=10,
            memory_staleness=0.75, memory_relevance=0.8, plan_currency=0.8,
            world_model_coverage=0.8, context_size_estimate=2000,
            coherence_score=0.8, composite_health=75.0,
        )
        issues = monitor.diagnose(snap)
        staleness = [i for i in issues if i.category == "staleness"]
        assert len(staleness) == 1
        assert staleness[0].severity == "warning"

    def test_staleness_critical(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="very_stale", tick=100, memory_count=10,
            memory_staleness=0.95, memory_relevance=0.8, plan_currency=0.8,
            world_model_coverage=0.8, context_size_estimate=2000,
            coherence_score=0.8, composite_health=70.0,
        )
        issues = monitor.diagnose(snap)
        staleness = [i for i in issues if i.category == "staleness"]
        assert staleness[0].severity == "critical"

    def test_plan_drift_warning(self) -> None:
        """plan_currency <= 0.4 is warning, <= 0.2 is critical."""
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="drift", tick=100, memory_count=10,
            memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.3,
            world_model_coverage=0.8, context_size_estimate=2000,
            coherence_score=0.6, composite_health=60.0,
        )
        issues = monitor.diagnose(snap)
        drift = [i for i in issues if i.category == "plan_drift"]
        assert len(drift) >= 1
        assert drift[0].severity == "warning"

    def test_plan_drift_critical(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="lost", tick=100, memory_count=10,
            memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.1,
            world_model_coverage=0.8, context_size_estimate=2000,
            coherence_score=0.6, composite_health=50.0,
        )
        issues = monitor.diagnose(snap)
        drift_crit = [i for i in issues if i.category == "plan_drift" and i.severity == "critical"]
        assert len(drift_crit) == 1

    def test_overload_warning(self) -> None:
        """CONTEXT_SIZE_WARNING threshold triggers warning."""
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="fat", tick=50, memory_count=300,
            memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.8,
            world_model_coverage=0.8, context_size_estimate=60000,
            coherence_score=0.8, composite_health=75.0,
        )
        issues = monitor.diagnose(snap)
        overload = [i for i in issues if i.category == "overload"]
        assert len(overload) == 1
        assert overload[0].severity == "warning"

    def test_overload_critical(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="huge", tick=50, memory_count=600,
            memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.8,
            world_model_coverage=0.8, context_size_estimate=150000,
            coherence_score=0.8, composite_health=70.0,
        )
        issues = monitor.diagnose(snap)
        overload = [i for i in issues if i.category == "overload"]
        assert overload[0].severity == "critical"

    def test_coherence_critical(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="incoherent", tick=10, memory_count=10,
            memory_staleness=0.2, memory_relevance=0.3, plan_currency=0.3,
            world_model_coverage=0.3, context_size_estimate=2000,
            coherence_score=0.25, composite_health=25.0,
        )
        issues = monitor.diagnose(snap)
        coh = [i for i in issues if i.category == "coherence"]
        assert len(coh) >= 1
        assert any(i.severity == "critical" for i in coh)

    def test_relevance_warning(self) -> None:
        """relevance <= 0.4 is warning, <= 0.2 is critical."""
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="irrelevant", tick=10, memory_count=10,
            memory_staleness=0.2, memory_relevance=0.3, plan_currency=0.8,
            world_model_coverage=0.8, context_size_estimate=2000,
            coherence_score=0.6, composite_health=65.0,
        )
        issues = monitor.diagnose(snap)
        rel = [i for i in issues if i.category == "relevance"]
        assert len(rel) >= 1
        assert rel[0].severity == "warning"

    def test_issues_sorted_critical_first(self) -> None:
        monitor = ContextHealthMonitor()
        snap = ContextQualitySnapshot(
            agent_name="mixed", tick=100, memory_count=500,
            memory_staleness=0.75, memory_relevance=0.1, plan_currency=0.1,
            world_model_coverage=0.0, context_size_estimate=150000,
            coherence_score=0.1, composite_health=10.0,
        )
        issues = monitor.diagnose(snap)
        assert len(issues) > 0
        assert issues[0].severity == "critical"


# ---------------------------------------------------------------------------
# ContextHealthMonitor — history
# ---------------------------------------------------------------------------

class TestContextHealthHistory:
    """测试快照历史管理。"""

    def test_history_with_limit(self) -> None:
        monitor = ContextHealthMonitor(max_history=10)
        monitor._history["a"] = [
            ContextQualitySnapshot(agent_name="a", tick=i) for i in range(5)
        ]
        hist = monitor.history("a", limit=3)
        assert len(hist) == 3
        assert hist[-1].tick == 4

    def test_history_default_limit(self) -> None:
        monitor = ContextHealthMonitor()
        monitor._history["b"] = [
            ContextQualitySnapshot(agent_name="b", tick=1),
            ContextQualitySnapshot(agent_name="b", tick=2),
        ]
        hist = monitor.history("b")
        assert len(hist) == 2

    def test_history_unknown_agent_empty(self) -> None:
        monitor = ContextHealthMonitor()
        assert monitor.history("nobody") == []


# ---------------------------------------------------------------------------
# ContextOptimizer
# ---------------------------------------------------------------------------

class TestContextOptimizer:
    """测试优化建议生成。"""

    def test_staleness_generates_repeat_memories(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="s", tick=10, memory_staleness=0.8)
        issues = [ContextIssue(severity="warning", category="staleness", description="x")]
        actions = opt.recommend(snap, issues)
        assert any(a.action_type == "repeat_memories" for a in actions)

    def test_overload_generates_compress(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="o", tick=10, context_size_estimate=60000)
        issues = [ContextIssue(severity="warning", category="overload", description="x")]
        actions = opt.recommend(snap, issues)
        assert any(a.action_type == "compress_memories" for a in actions)

    def test_plan_drift_generates_restore(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="p", tick=10, plan_currency=0.1)
        issues = [ContextIssue(severity="critical", category="plan_drift", description="x")]
        actions = opt.recommend(snap, issues)
        assert any(a.action_type == "restore_plan" for a in actions)

    def test_multiple_issues_multiple_actions(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="m", tick=10)
        issues = [
            ContextIssue(severity="warning", category="staleness", description="a"),
            ContextIssue(severity="critical", category="overload", description="b"),
            ContextIssue(severity="warning", category="relevance", description="c"),
        ]
        actions = opt.recommend(snap, issues)
        assert len(actions) == 3

    def test_duplicate_category_only_one_action(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="d", tick=10, memory_staleness=0.8)
        issues = [
            ContextIssue(severity="warning", category="staleness", description="a"),
            ContextIssue(severity="critical", category="staleness", description="b"),
        ]
        actions = opt.recommend(snap, issues)
        assert len(actions) == 1

    def test_actions_sorted_by_priority_desc(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="s", tick=10, memory_staleness=0.8, plan_currency=0.1)
        issues = [
            ContextIssue(severity="warning", category="staleness", description="a"),
            ContextIssue(severity="critical", category="plan_drift", description="b"),
        ]
        actions = opt.recommend(snap, issues)
        assert actions[0].priority >= actions[1].priority

    def test_empty_issues_empty_actions(self) -> None:
        opt = ContextOptimizer()
        snap = ContextQualitySnapshot(agent_name="e", tick=10)
        actions = opt.recommend(snap, [])
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# Fake agent for snapshot() testing (matches subagent's attribute patterns)
# ---------------------------------------------------------------------------

class _FakeMemory:
    """Fake memory entry with tick_index (used by subagent's snapshot)."""
    def __init__(self, description: str, tick_index: int):
        self.description = description
        self.tick_index = tick_index


class _FakeMemoryObj:
    """Fake memory container with .entries attribute."""
    def __init__(self, entries: list[_FakeMemory]):
        self.entries = entries


class _FakePlanCheckpoint:
    """Fake plan checkpoint with tick_created and tick_expires."""
    def __init__(self, tick_created: int, tick_expires: int | None = None):
        self.tick_created = tick_created
        self.tick_expires = tick_expires if tick_expires else tick_created + 48


class _FakePlanEngine:
    """Fake plan engine with get_active(agent_name)."""
    def __init__(self, checkpoint: _FakePlanCheckpoint | None = None):
        self._checkpoint = checkpoint

    def get_active(self, agent_name: str) -> _FakePlanCheckpoint | None:
        return self._checkpoint


class _FakeWorldModel:
    """Fake world model with get_snapshot()."""
    def __init__(self, rules_count: int = 0, episodes_count: int = 1):
        self._rules_count = rules_count
        self._episodes_count = episodes_count

    def get_snapshot(self) -> dict:
        return {
            "rules_count": self._rules_count,
            "episodes_count": self._episodes_count,
        }


class _FakeAgent:
    """Fake agent matching subagent's snapshot() attribute access patterns.

    Subagent checks:
    - agent.memory.entries (not agent.memory_stream.memories)
    - agent._plan_engine or agent._get_plan_engine()
    - agent.world_model.get_snapshot()
    """

    def __init__(
        self,
        name: str,
        memory_count: int = 0,
        memory_tick: int = 0,
        plan_tick: int = 0,
        rule_count: int = 0,
        episode_count: int = 0,
    ):
        self.name = name
        entries = [
            _FakeMemory(description=f"memory_{i}", tick_index=memory_tick)
            for i in range(memory_count)
        ]
        self.memory = _FakeMemoryObj(entries)
        self.current_plan = "explore the forest and find food" if memory_count > 0 else ""
        self._plan_engine = _FakePlanEngine(
            _FakePlanCheckpoint(plan_tick) if plan_tick > 0 else None
        )
        self.world_model = _FakeWorldModel(
            rules_count=rule_count,
            episodes_count=max(episode_count, 1),
        )


class TestSnapshotWithFakeAgent:
    """测试 snapshot() 方法与假 agent 集成。"""

    def test_snapshot_with_memories(self) -> None:
        monitor = ContextHealthMonitor()
        agent = _FakeAgent("agumon", memory_count=5, memory_tick=8, plan_tick=2,
                           rule_count=3, episode_count=10)
        snap = monitor.snapshot(agent, tick=10)
        assert snap.agent_name == "agumon"
        assert snap.memory_count == 5
        assert snap.memory_staleness > 0

    def test_snapshot_no_memories(self) -> None:
        monitor = ContextHealthMonitor()
        agent = _FakeAgent("blank", memory_count=0, plan_tick=0)
        snap = monitor.snapshot(agent, tick=0)
        assert snap.memory_count == 0
        assert snap.memory_staleness == 0.0

    def test_snapshot_history_grows(self) -> None:
        monitor = ContextHealthMonitor(max_history=5)
        agent = _FakeAgent("gabu", memory_count=3, memory_tick=0, plan_tick=1)
        for t in range(3):
            monitor.snapshot(agent, tick=t)
        hist = monitor.history("gabu")
        assert len(hist) == 3

    def test_snapshot_coherence_computed(self) -> None:
        monitor = ContextHealthMonitor()
        agent = _FakeAgent("tai", memory_count=3, memory_tick=1, plan_tick=1,
                           rule_count=5, episode_count=10)
        snap = monitor.snapshot(agent, tick=2)
        assert 0.0 <= snap.coherence_score <= 1.0

    def test_snapshot_composite_health_range(self) -> None:
        monitor = ContextHealthMonitor()
        agent = _FakeAgent("sora", memory_count=3, memory_tick=1, plan_tick=1,
                           rule_count=5, episode_count=10)
        snap = monitor.snapshot(agent, tick=2)
        assert 0.0 <= snap.composite_health <= 100.0
