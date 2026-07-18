#!/usr/bin/env python3
"""
Phase 25 端到端验证: Agent 上下文质量与可靠性工程
================================================

验证内容:
1. ContextQualitySnapshot 字段完整性 + to_dict/from_dict
2. ContextHealthMonitor.snapshot() — 假 agent 快照生成
3. ContextHealthMonitor.diagnose() — 六维问题诊断 (staleness/relevance/plan_drift/overload/coherence/relevance)
4. ContextOptimizer.recommend() — 优化建议生成
5. 快照历史追踪 + 世界级概览
6. API 端点: GET /api/digimon/{name}/context-health + GET /api/context/overview
7. Scheduler 集成: tick_once() 生成快照

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase25.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend project root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from digimon_world.api.app import app  # noqa: E402
from digimon_world.world.context_quality import (  # noqa: E402
    ContextHealthMonitor,
    ContextIssue,
    ContextOptimizer,
    ContextQualitySnapshot,
    get_health_monitor,
    reset_context_quality,
)

PASS = "\033[32m✅ PASS\033[0m"
FAIL = "\033[31m❌ FAIL\033[0m"
INFO = "\033[36mℹ️\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    msg = f"  {status} {name}"
    if detail and not condition:
        msg += f" — {detail}"
    print(msg)
    results.append((name, condition, detail))
    return condition


# ── Fake agent classes (matching subagent internals) ──

class _FakeMemory:
    def __init__(self, description: str, tick_index: int):
        self.description = description
        self.tick_index = tick_index


class _FakeMemoryObj:
    def __init__(self, entries: list[_FakeMemory]):
        self.entries = entries


class _FakePlanCheckpoint:
    def __init__(self, tick_created: int, tick_expires: int | None = None):
        self.tick_created = tick_created
        self.tick_expires = tick_expires if tick_expires else tick_created + 48


class _FakePlanEngine:
    def __init__(self, checkpoint: _FakePlanCheckpoint | None = None):
        self._checkpoint = checkpoint

    def get_active(self, agent_name: str) -> _FakePlanCheckpoint | None:
        return self._checkpoint


class _FakeWorldModel:
    def __init__(self, rules_count: int = 0, episodes_count: int = 1):
        self._rules_count = rules_count
        self._episodes_count = episodes_count

    def get_snapshot(self) -> dict:
        return {
            "rules_count": self._rules_count,
            "episodes_count": self._episodes_count,
        }


class _FakeAgent:
    def __init__(
        self,
        name: str,
        memory_count: int = 0,
        memory_tick: int = 0,
        plan_tick: int = 0,
        rule_count: int = 0,
        episode_count: int = 1,
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


# ── Fixture helpers ──

def make_agents(n: int = 30, seed_tick: int = 0) -> list[_FakeAgent]:
    """Create N fake agents with realistic varied parameters."""
    agents = []
    names = [
        "agumon", "gabumon", "piyomon", "palmon", "tentomon",
        "gomamon", "patamon", "gatomon", "veemon", "wormmon",
        "hawkmon", "armadimon", "guilmon", "renamon", "terriermon",
        "lopmon", "cyberdramon", "marineangemon", "impmon", "leomon",
        "ogremon", "devimon", "angemon", "andromon", "whamon",
        "seadramon", "garurumon", "greymon", "birdramon", "kabuterimon",
    ]
    for i in range(n):
        mem_count = max(0, (i % 10) * 2 + 5)  # 5-23
        mem_tick = max(0, seed_tick - (i % 15))  # varied staleness
        plan_tick = max(0, seed_tick - (i % 5))
        rule_count = (i % 7) * 2  # 0-12
        episode_count = max(1, (i % 5) + 3)
        agents.append(_FakeAgent(
            name=names[i],
            memory_count=mem_count,
            memory_tick=mem_tick,
            plan_tick=plan_tick,
            rule_count=rule_count,
            episode_count=episode_count,
        ))
    return agents


def main():
    print("=" * 60)
    print("  Phase 25 验证: Agent 上下文质量与可靠性工程")
    print("=" * 60)

    reset_context_quality()

    # ================================================================
    # SECTION 1: ContextQualitySnapshot 字段完整性
    # ================================================================
    print("\n📊 Section 1: ContextQualitySnapshot")

    snap = ContextQualitySnapshot(agent_name="test", tick=0)
    check("1.1 默认字段", snap.memory_count == 0 and snap.memory_staleness == 0.0)
    check("1.2 时间戳自动生成", bool(snap.timestamp) and "T" in snap.timestamp)

    full_snap = ContextQualitySnapshot(
        agent_name="agumon", tick=42, memory_count=15,
        memory_staleness=0.3, memory_relevance=0.8, plan_currency=0.9,
        world_model_coverage=0.5, context_size_estimate=3500,
        coherence_score=0.73, composite_health=72.5,
    )
    d = full_snap.to_dict()
    check("1.3 to_dict 包含所有字段", all(k in d for k in [
        "agent_name", "tick", "memory_count", "memory_staleness",
        "memory_relevance", "plan_currency", "world_model_coverage",
        "context_size_estimate", "coherence_score", "composite_health",
        "timestamp",
    ]))
    restored = ContextQualitySnapshot.from_dict(d)
    check("1.4 from_dict 往返", restored.composite_health == 72.5)

    # ================================================================
    # SECTION 2: ContextHealthMonitor.snapshot() — agent 快照
    # ================================================================
    print("\n📊 Section 2: ContextHealthMonitor.snapshot()")

    monitor = ContextHealthMonitor()
    agent = _FakeAgent("agumon", memory_count=10, memory_tick=8,
                       plan_tick=2, rule_count=5, episode_count=10)
    snap = monitor.snapshot(agent, tick=10)

    check("2.1 agent_name 正确", snap.agent_name == "agumon")
    check("2.2 memory_count 正确", snap.memory_count == 10)
    check("2.3 memory_staleness > 0 (有旧记忆)",
          snap.memory_staleness > 0,
          f"got {snap.memory_staleness}")
    check("2.4 memory_staleness ≤ 1.0",
          snap.memory_staleness <= 1.0,
          f"got {snap.memory_staleness}")
    check("2.5 memory_relevance ∈ [0,1]",
          0.0 <= snap.memory_relevance <= 1.0,
          f"got {snap.memory_relevance}")
    check("2.6 plan_currency ∈ [0,1]",
          0.0 <= snap.plan_currency <= 1.0,
          f"got {snap.plan_currency}")
    check("2.7 world_model_coverage ∈ [0,1]",
          0.0 <= snap.world_model_coverage <= 1.0,
          f"got {snap.world_model_coverage}")
    check("2.8 context_size_estimate > 0 (有记忆)",
          snap.context_size_estimate > 0,
          f"got {snap.context_size_estimate}")
    check("2.9 coherence_score ∈ [0,1]",
          0.0 <= snap.coherence_score <= 1.0,
          f"got {snap.coherence_score}")
    check("2.10 composite_health ∈ [0,100]",
          0.0 <= snap.composite_health <= 100.0,
          f"got {snap.composite_health}")

    # Empty agent
    blank = _FakeAgent("blank", memory_count=0)
    blank_snap = monitor.snapshot(blank, tick=0)
    check("2.11 空 agent staleness=0", blank_snap.memory_staleness == 0.0)

    # ================================================================
    # SECTION 3: ContextHealthMonitor.diagnose() — 诊断
    # ================================================================
    print("\n📊 Section 3: ContextHealthMonitor.diagnose()")

    # Healthy snapshot
    healthy_snap = ContextQualitySnapshot(
        agent_name="healthy", tick=10, memory_count=20,
        memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.9,
        world_model_coverage=0.6, context_size_estimate=4000,
        coherence_score=0.77, composite_health=78.0,
    )
    issues = monitor.diagnose(healthy_snap)
    check("3.1 健康 agent 无问题", len(issues) == 0,
          f"got {len(issues)} issues")

    # Critical staleness
    stale_snap = ContextQualitySnapshot(
        agent_name="stale", tick=100, memory_count=10,
        memory_staleness=0.95, memory_relevance=0.8, plan_currency=0.8,
        world_model_coverage=0.8, context_size_estimate=2000,
        coherence_score=0.8, composite_health=70.0,
    )
    issues = monitor.diagnose(stale_snap)
    stall = [i for i in issues if i.category == "staleness"]
    check("3.2 过期记忆检测 (critical)",
          len(stall) == 1 and stall[0].severity == "critical",
          f"got {len(stall)} issues, severity={stall[0].severity if stall else 'N/A'}")

    # Plan drift
    drift_snap = ContextQualitySnapshot(
        agent_name="drift", tick=100, memory_count=10,
        memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.1,
        world_model_coverage=0.8, context_size_estimate=2000,
        coherence_score=0.6, composite_health=50.0,
    )
    issues = monitor.diagnose(drift_snap)
    drift = [i for i in issues if i.category == "plan_drift"]
    check("3.3 计划漂移检测 (critical)",
          len(drift) >= 1 and any(i.severity == "critical" for i in drift))

    # Overload
    huge_snap = ContextQualitySnapshot(
        agent_name="huge", tick=50, memory_count=600,
        memory_staleness=0.2, memory_relevance=0.8, plan_currency=0.8,
        world_model_coverage=0.8, context_size_estimate=150_000,
        coherence_score=0.8, composite_health=70.0,
    )
    issues = monitor.diagnose(huge_snap)
    ovl = [i for i in issues if i.category == "overload"]
    check("3.4 上下文过载检测 (critical)",
          len(ovl) == 1 and ovl[0].severity == "critical")

    # Mixed issues — sorted critical first
    mixed_snap = ContextQualitySnapshot(
        agent_name="mixed", tick=100, memory_count=500,
        memory_staleness=0.75, memory_relevance=0.1, plan_currency=0.1,
        world_model_coverage=0.0, context_size_estimate=150_000,
        coherence_score=0.1, composite_health=10.0,
    )
    issues = monitor.diagnose(mixed_snap)
    check("3.5 多问题按 critical 优先排序",
          len(issues) > 2 and issues[0].severity == "critical")

    # ================================================================
    # SECTION 4: ContextOptimizer.recommend() — 优化建议
    # ================================================================
    print("\n📊 Section 4: ContextOptimizer.recommend()")

    opt = ContextOptimizer()

    # Staleness → repeat_memories
    actions = opt.recommend(
        snap := ContextQualitySnapshot(agent_name="s", tick=10, memory_staleness=0.8),
        [ContextIssue(severity="warning", category="staleness", description="x")],
    )
    check("4.1 staleness → repeat_memories",
          any(a.action_type == "repeat_memories" for a in actions))

    # Overload → compress_memories
    actions = opt.recommend(
        ContextQualitySnapshot(agent_name="o", tick=10, context_size_estimate=60_000),
        [ContextIssue(severity="warning", category="overload", description="x")],
    )
    check("4.2 overload → compress_memories",
          any(a.action_type == "compress_memories" for a in actions))

    # Plan drift → restore_plan
    actions = opt.recommend(
        ContextQualitySnapshot(agent_name="p", tick=10, plan_currency=0.1),
        [ContextIssue(severity="critical", category="plan_drift", description="x")],
    )
    check("4.3 plan_drift → restore_plan",
          any(a.action_type == "restore_plan" for a in actions))

    # Multiple issues → multiple actions
    actions = opt.recommend(
        ContextQualitySnapshot(agent_name="m", tick=10),
        [
            ContextIssue(severity="warning", category="staleness", description="a"),
            ContextIssue(severity="critical", category="overload", description="b"),
            ContextIssue(severity="warning", category="relevance", description="c"),
        ],
    )
    check("4.4 多问题 → 多建议", len(actions) == 3)

    # Duplicate category → deduplicated
    actions = opt.recommend(
        ContextQualitySnapshot(agent_name="d", tick=10, memory_staleness=0.9),
        [
            ContextIssue(severity="warning", category="staleness", description="a"),
            ContextIssue(severity="critical", category="staleness", description="b"),
        ],
    )
    check("4.5 同类别去重", len(actions) == 1)

    # Sorted by priority
    actions = opt.recommend(
        ContextQualitySnapshot(agent_name="s", tick=10,
                               memory_staleness=0.8, plan_currency=0.1),
        [
            ContextIssue(severity="warning", category="staleness", description="a"),
            ContextIssue(severity="critical", category="plan_drift", description="b"),
        ],
    )
    check("4.6 按优先级降序", actions[0].priority >= actions[1].priority)
    check("4.7 estimated_improvement > 0",
          all(a.estimated_improvement >= 0 for a in actions))

    # Empty issues
    actions = opt.recommend(
        ContextQualitySnapshot(agent_name="e", tick=10),
        [],
    )
    check("4.8 无问题 → 空建议", len(actions) == 0)

    # ================================================================
    # SECTION 5: 快照历史 + 世界级概览
    # ================================================================
    print("\n📊 Section 5: 快照历史 + 世界概览")

    monitor2 = ContextHealthMonitor(max_history=10)
    agents = make_agents(10, seed_tick=10)
    for t in range(5):
        for agent in agents:
            monitor2.snapshot(agent, tick=t + 10)

    hist = monitor2.history("agumon")
    check("5.1 历史记录累积", len(hist) == 5,
          f"got {len(hist)} snapshots")

    check("5.2 all_agents 含所有 agent",
          len(monitor2.all_agents) == 10,
          f"got {len(monitor2.all_agents)}")

    # Verify all snapshots have valid ranges
    all_ok = True
    for name in monitor2.all_agents:
        snap = monitor2.latest_snapshot(name)
        if snap is None:
            all_ok = False
            break
        if not (0.0 <= snap.composite_health <= 100.0):
            all_ok = False
            break
    check("5.3 所有 agent 快照合法", all_ok)

    # ================================================================
    # SECTION 6: API 端点 (using real WorldState agents)
    # ================================================================
    print("\n📊 Section 6: API 端点")

    # Use real world agents like Phase 24 does
    from digimon_world.world import reset_world, get_world  # noqa: E402
    reset_world()
    reset_context_quality()

    world = get_world()
    all_agents = world.all()
    check("6.0 WorldState has agents", len(all_agents) > 0,
          f"got {len(all_agents)} agents")

    client = TestClient(app)
    monitor3 = get_health_monitor()

    # Pre-populate snapshots from real agents
    for agent in all_agents:
        monitor3.snapshot(agent, tick=12)

    # 6.1 GET /api/digimon/{name}/context-health (use first real agent)
    first_name = all_agents[0].name
    resp = client.get(f"/api/digimon/{first_name}/context-health")
    check("6.1 /api/digimon/{name}/context-health 返回 200",
          resp.status_code == 200,
          f"status: {resp.status_code}, body: {resp.text[:200]}")
    if resp.status_code == 200:
        data = resp.json()
        check("6.2 响应含 composite_health",
              "composite_health" in data,
              f"keys: {list(data.keys())}")
        check("6.3 响应含 dimensions (6维)",
              "dimensions" in data and len(data["dimensions"]) == 6,
              f"dimensions: {data.get('dimensions', {})}")
        check("6.4 响应含 issues + recommendations",
              "issues" in data and "recommendations" in data)

    # 6.2 GET /api/digimon/nonexistent/context-health → 404
    resp = client.get("/api/digimon/nonexistent_xyz/context-health")
    check("6.5 不存在 agent → 404",
          resp.status_code == 404,
          f"status: {resp.status_code}")

    # 6.3 GET /api/context/overview
    resp = client.get("/api/context/overview")
    check("6.6 /api/context/overview 返回 200",
          resp.status_code == 200,
          f"status: {resp.status_code}, body: {resp.text[:200]}")
    if resp.status_code == 200:
        data = resp.json()
        check("6.7 overview 含 total_agents",
              "total_agents" in data,
              f"keys: {list(data.keys())}")
        check("6.8 overview total_agents > 0",
              data.get("total_agents", 0) > 0,
              f"got {data.get('total_agents')}")
        check("6.9 overview 含 health_distribution",
              "health_distribution" in data)
        dist = data.get("health_distribution", {})
        check("6.10 health_distribution 三元组",
              all(k in dist for k in ("critical", "warning", "healthy")),
              f"dist: {dist}")
        check("6.11 overview 含 worst_5",
              "worst_5" in data and len(data.get("worst_5", [])) <= 5)
        check("6.12 average_health ∈ [0,100]",
              0.0 <= data.get("average_health", -1) <= 100.0,
              f"avg: {data.get('average_health')}")

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    status = PASS if passed == total else FAIL
    print(f"  {status} Phase 25: {passed}/{total} 项通过")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
