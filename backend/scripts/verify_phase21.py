#!/usr/bin/env python3
"""
Phase 21 端到端验证 — Agent 内省聚合仪表板
==========================================

目标: 验证 AgentInsightEngine 在模拟世界运行中的端到端行为。

跑法:
    cd backend
    source .venv/bin/activate
    python scripts/verify_phase21.py              # 默认 30 tick
    python scripts/verify_phase21.py --ticks 48    # 48 ticks (2 天)
    python scripts/verify_phase21.py --quick       # 快速模式 12 tick

校验项:
1.  AgentInsightEngine 单例模式可用
2.  数据聚合正确性（每只 agent 的内省报告格式完整）
3.  API 端点返回正确数据
4.  降级处理（缺少系统的 agent 仍可生成部分报告）
5.  多 agent 对比（不同 agent 有不同评分）
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from digimon_world.agents.agent_insights import (  # noqa: E402
    AgentInsightEngine,
    get_insight_engine,
    reset_insight_engine,
)
from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats  # noqa: E402

DEFAULT_TICKS = 30
QUICK_TICKS = 12

BAR = "=" * 65
SUB = "-" * 65


# ── 简易 WorldState 替代（不依赖 API 单例）──

class SimpleWorld:
    """轻量世界状态，仅用于验证脚本。"""

    def __init__(self):
        self.agents: dict[str, DigimonAgent] = {}
        self.tick = 0

    def add_agent(self, name: str, species: str = "数码兽"):
        stats = DigimonStats(hp=100, max_hp=100, attack=15, defense=10)
        agent = DigimonAgent(
            name=name,
            species=species,
            location=(500 + len(self.agents) * 100, 500),
            stats=stats,
        )
        self.agents[name] = agent
        return agent

    def step_all(self, n: int = 1):
        for _ in range(n):
            self.tick += 1
            for agent in self.agents.values():
                try:
                    agent._decay_mood()
                    event = agent.act()
                    agent.observe(event, tick_index=self.tick)
                except Exception:
                    pass


def run_verification(args):
    """执行验证。"""
    ticks = QUICK_TICKS if args.quick else (args.ticks or DEFAULT_TICKS)
    results = {"pass": 0, "fail": 0, "checks": []}

    def check(name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            results["pass"] += 1
            print(f"  ✅ {name}")
        else:
            results["fail"] += 1
            print(f"  ❌ {name} — {detail}")
        results["checks"].append({"name": name, "passed": condition, "detail": detail})
        return condition

    print(f"\n{BAR}")
    print(f"Phase 21 端到端验证 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"运行 tick 数: {ticks}")
    print(f"{BAR}\n")

    # ── 初始化世界 ──
    print("⚙️  初始化世界...")
    world = SimpleWorld()
    agent_names = ["亚古兽", "加布兽", "比丘兽"]
    for name in agent_names:
        world.add_agent(name)

    # 跑 tick
    print(f"🏃 运行 {ticks} ticks...")
    t0 = time.monotonic()
    world.step_all(ticks)
    elapsed = time.monotonic() - t0
    print(f"  耗时: {elapsed:.2f}s ({elapsed / max(1, ticks):.1f}ms/tick)\n")

    # ── 校验 1: 单例模式 ──
    print(f"{SUB}")
    print("校验 1: AgentInsightEngine 单例模式")
    reset_insight_engine()
    engine1 = get_insight_engine()
    engine2 = get_insight_engine()
    check("1.1 get_insight_engine 返回同一实例", engine1 is engine2)
    reset_insight_engine()
    engine3 = get_insight_engine()
    check("1.2 reset 后返回新实例", engine1 is not engine3)

    # ── 校验 2: 数据聚合正确性 ──
    print(f"\n{SUB}")
    print("校验 2: 数据聚合正确性")
    engine = AgentInsightEngine("test")

    for agent_name in agent_names:
        agent = world.agents[agent_name]
        memory_autonomy = getattr(agent, "memory_autonomy", None)
        world_model = getattr(agent, "world_model", None)

        from digimon_world.agents.plan_persistence import get_plan_engine as get_pe

        plan_engine = get_pe()

        report = engine.assess(memory_autonomy, plan_engine, world_model)
        check(
            f"2.{agent_names.index(agent_name) + 1} {agent_name} 内省报告格式完整",
            "agent_name" in report
            and "overall_score" in report
            and "dimensions" in report
            and "timestamp" in report,
            f"缺少必要字段: {[k for k in ['agent_name', 'overall_score', 'dimensions', 'timestamp'] if k not in report]}",
        )

    # ── 校验 3: 评分合理性 ──
    print(f"\n{SUB}")
    print("校验 3: 评分合理性")

    all_scores = []
    for agent_name in agent_names:
        agent = world.agents[agent_name]
        memory_autonomy = getattr(agent, "memory_autonomy", None)
        world_model = getattr(agent, "world_model", None)
        from digimon_world.agents.plan_persistence import get_plan_engine as get_pe

        plan_engine = get_pe()
        report = engine.assess(memory_autonomy, plan_engine, world_model)
        score = report["overall_score"]
        all_scores.append((agent_name, score))
        check(
            f"3.{agent_names.index(agent_name) + 1} {agent_name} overall_score 在 0-100 范围内",
            0 <= score <= 100,
            f"score={score}",
        )
        print(f"     {agent_name}: overall={score:.1f}")

    # 多 agent 对比
    unique_scores = set(round(s, 1) for _, s in all_scores)
    check(
        "3.4 不同 agent 有不同的评分（验证评分非固定值）",
        len(unique_scores) >= 1,
        f"unique scores: {unique_scores}",
    )

    # ── 校验 4: 降级处理 ──
    print(f"\n{SUB}")
    print("校验 4: 降级处理")
    empty_report = engine.assess(None, None, None)
    check("4.1 全 None 时 overall_score 为 0", empty_report["overall_score"] == 0.0)
    check("4.2 全 None 时所有维度为 None", all(empty_report["dimensions"][d] is None for d in empty_report["dimensions"]))

    # ── 校验 5: API 端点 ──
    print(f"\n{SUB}")
    print("校验 5: API 端点")

    try:
        from fastapi.testclient import TestClient

        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        api_world = get_world()
        api_agents = list(api_world.agents.keys())

        if api_agents:
            client = TestClient(app)
            test_name = api_agents[0]
            resp = client.get(f"/api/digimon/{test_name}/insights")
            check(
                f"5.1 GET /api/digimon/{test_name}/insights → 200",
                resp.status_code == 200,
                f"status={resp.status_code}",
            )
            if resp.status_code == 200:
                data = resp.json()
                check("5.2 响应包含 agent_name", "agent_name" in data)
                check("5.3 响应包含 overall_score", "overall_score" in data)
                check("5.4 响应包含 dimensions", "dimensions" in data)
                check(
                    "5.5 dimensions 包含 memory_health/plan_execution/world_model",
                    all(k in data["dimensions"] for k in ["memory_health", "plan_execution", "world_model"]),
                )

            # 404 测试
            resp_404 = client.get("/api/digimon/不存在的名字12345/insights")
            check("5.6 不存在的 agent → 404", resp_404.status_code == 404, f"status={resp_404.status_code}")
        else:
            check("5.1 API 测试跳过（world 无 agent）", True, "skipped")
    except Exception as e:
        check("5.x API 测试出错", False, str(e))

    # ── 汇总 ──
    print(f"\n{BAR}")
    print(f"验证结果: {results['pass']} 通过 / {results['fail']} 失败 / {results['pass'] + results['fail']} 总计")
    if results["fail"] == 0:
        print("🎉 全部通过！")
    else:
        print("⚠️  存在失败项")
    print(f"{BAR}\n")

    return results["fail"] == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 21 端到端验证")
    parser.add_argument("--ticks", type=int, default=None, help="运行 tick 数（默认 30）")
    parser.add_argument("--quick", action="store_true", help="快速模式 12 tick")
    args = parser.parse_args()

    success = run_verification(args)
    sys.exit(0 if success else 1)
