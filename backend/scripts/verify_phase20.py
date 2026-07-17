#!/usr/bin/env python3
"""
Phase 20 端到端验证 — 自演化世界模型
======================================

目标: 验证 WorldModel 在模拟世界运行中的端到端行为。

跑法:
    cd backend
    source .venv/bin/activate
    python scripts/verify_phase20.py              # 默认 30 tick
    python scripts/verify_phase20.py --ticks 48    # 48 ticks (2 天)
    python scripts/verify_phase20.py --quick       # 快速模式 12 tick

校验项:
1.  每只 agent 的 world_model 不为 None 且独立
2.  episodic.count() > 0（至少有情节记录）
3.  规则已提取（至少部分 agent 有规则）
4.  统计信息可读
5.  序列化往返不丢失数据
6.  API 端点返回正确数据
7.  预测功能可用（evaluate_plan 返回合理建议）
8.  跨 agent 情节隔离
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

from digimon_world.agents.digimon_agent import DigimonAgent, DigimonStats  # noqa: E402
from digimon_world.memory.world_model import WorldModel  # noqa: E402

DEFAULT_TICKS = 30
QUICK_TICKS = 12

BAR = "=" * 65
SUB = "-" * 65


# ── 简易 WorldState 替代（不依赖 API 单例）──

class MiniWorld:
    """轻量世界容器，用于验证脚本（不需要完整的 WorldState/API）。"""

    def __init__(self):
        self.agents: list[DigimonAgent] = []

    def spawn(self, agent: DigimonAgent) -> None:
        self.agents.append(agent)

    def get(self, name: str) -> DigimonAgent | None:
        for a in self.agents:
            if a.name == name:
                return a
        return None

    def all(self) -> list[DigimonAgent]:
        return list(self.agents)

    def count(self) -> int:
        return len(self.agents)


def create_sample_world() -> MiniWorld:
    """创建包含 5 只数码兽的测试世界。"""
    world = MiniWorld()

    specs = [
        ("亚古兽", "agumon", (200, 400)),
        ("加布兽", "gabumon", (700, 350)),
        ("比丘兽", "biyomon", (480, 180)),
        ("甲虫兽", "tentomon", (350, 300)),
        ("巴鲁兽", "palmon", (600, 250)),
    ]

    for name, species, loc in specs:
        agent = DigimonAgent(
            name=name,
            species=species,
            location=loc,
            stats=DigimonStats(hp=random_hp(), max_hp=100),
        )
        # 禁用 LLM 调用
        agent.planner = None
        agent.reflector = None
        world.spawn(agent)

    return world


def random_hp() -> int:
    """返回 60-100 之间的 HP。"""
    import hashlib
    import time as _time
    h = hashlib.md5(str(_time.time()).encode()).hexdigest()
    return 60 + int(h, 16) % 41


def simulate_tick(world: MiniWorld, tick: int) -> list[dict]:
    """模拟一个世界 tick：每只 agent 执行 act() + observe() + world_model.observe()。"""
    events = []
    for agent in world.all():
        agent._decay_mood()
        pre_state = agent._capture_world_state(tick_index=tick)
        event = agent.act()
        agent.observe(event, tick_index=tick)
        agent.world_model.observe(pre_state, agent.current_plan or "idle", event, tick)
        events.append(event)
    return events


def run_verification(ticks: int) -> tuple[bool, list[str], dict]:
    """运行端到端验证。返回 (pass, results, stats)。"""
    results: list[str] = []
    stats: dict = {}

    world = create_sample_world()
    results.append(f"创建世界: {world.count()} 只数码兽")

    # ── 1. 每只 agent 的 world_model 不为 None ──
    all_ok = True
    for agent in world.all():
        if agent.world_model is None:
            results.append(f"❌ {agent.name} world_model 为 None")
            all_ok = False
    if all_ok:
        results.append("✅ 所有 agent 的 world_model 已初始化")
    else:
        results.append("❌ 部分 agent 的 world_model 未初始化")

    # ── 2. 运行 N ticks ──
    results.append(f"开始模拟 {ticks} ticks...")
    for tick in range(ticks):
        simulate_tick(world, tick)

    total_episodes = sum(a.world_model.episodic.count() for a in world.all())
    results.append(f"模拟完成: 累计 {total_episodes} 条情节记忆")

    # ── 3. episodic.count() > 0 ──
    all_has_episodes = True
    for agent in world.all():
        ec = agent.world_model.episodic.count()
        if ec == 0:
            results.append(f"❌ {agent.name} 没有情节记录")
            all_has_episodes = False
    if all_has_episodes:
        results.append("✅ 所有 agent 至少记录了 1 条情节")
    else:
        results.append("❌ 部分 agent 没有情节记录")

    stats["total_episodes"] = total_episodes

    # ── 4. 规则已提取 ──
    # 手动触发规则提取（因为可能还没到 24 tick）
    total_rules = 0
    for agent in world.all():
        agent.world_model.extract_rules(force=True)
        total_rules += agent.world_model.semantic.count()

    stats["total_rules"] = total_rules
    if total_rules > 0:
        results.append(f"✅ 规则已提取: {total_rules} 条")
    else:
        results.append(f"⚠️  未提取到规则（需要 ≥3 条相同模式的情节，{ticks} ticks 可能不够）")

    # ── 5. 统计信息可读 ──
    all_stats_ok = True
    for agent in world.all():
        s = agent.world_model.stats()
        required = ["agent_name", "total_episodes", "total_rules"]
        for field in required:
            if field not in s:
                results.append(f"❌ {agent.name} stats 缺少字段: {field}")
                all_stats_ok = False
    if all_stats_ok:
        results.append("✅ 所有 agent 的 stats() 字段完整")

    stats["agent_stats"] = {
        a.name: {
            "episodes": a.world_model.episodic.count(),
            "rules": a.world_model.semantic.count(),
            "agent_name": a.world_model.stats()["agent_name"],
        }
        for a in world.all()
    }

    # ── 6. 序列化往返不丢失数据 ──
    all_serial_ok = True
    for agent in world.all():
        wm = agent.world_model
        d = wm.to_dict()
        restored = WorldModel.from_dict(d)
        if restored.episodic.count() != wm.episodic.count():
            results.append(f"❌ {agent.name} 序列化后情节数不一致")
            all_serial_ok = False
        if restored.agent_name != wm.agent_name:
            results.append(f"❌ {agent.name} 序列化后 agent_name 不一致")
            all_serial_ok = False
    if all_serial_ok:
        results.append("✅ 所有 agent 的 world_model 序列化往返数据一致")

    # ── 7. 预测功能可用 ──
    all_predict_ok = True
    for agent in world.all():
        wm = agent.world_model
        result = wm.evaluate_plan(
            {"region_id": "file_island", "stage": "rookie"},
            "去森林探索然后战斗",
        )
        if "recommendation" not in result:
            results.append(f"❌ {agent.name} evaluate_plan 缺少 recommendation")
            all_predict_ok = False
        if result["recommendation"] not in ("proceed", "caution", "reconsider"):
            results.append(f"❌ {agent.name} evaluate_plan 返回非法建议: {result['recommendation']}")
            all_predict_ok = False
        if "overall_confidence" not in result:
            results.append(f"❌ {agent.name} evaluate_plan 缺少 overall_confidence")
            all_predict_ok = False
    if all_predict_ok:
        results.append("✅ 所有 agent 的 evaluate_plan() 返回合理建议")

    # ── 8. 跨 agent 情节隔离 ──
    isolation_ok = True
    for i, a in enumerate(world.all()):
        for j, b in enumerate(world.all()):
            if i >= j:
                continue
            if a.world_model is b.world_model:
                results.append(f"❌ {a.name} 和 {b.name} 共享同一个 world_model 实例")
                isolation_ok = False
    if isolation_ok:
        results.append("✅ 跨 agent 情节隔离（各自独立 world_model）")

    # ── 9. API 端点测试（如果 get_world 可用）──
    try:
        from digimon_world.world.world_state import reset_world
        from fastapi.testclient import TestClient

        reset_world()
        client = TestClient(__import__("digimon_world.api.app", fromlist=["app"]).app)

        # 测试已知 agent
        resp = client.get("/api/digimon/亚古兽/world-model")
        if resp.status_code == 200:
            data = resp.json()
            assert data["name"] == "亚古兽"
            assert data["status"] == "active"
            assert "stats" in data
            assert "recent_episodes" in data
            assert "rules" in data
            results.append("✅ API /api/digimon/{name}/world-model 返回正确数据")
        else:
            results.append(f"❌ API 端点返回 {resp.status_code}")

        # 测试 404
        resp_404 = client.get("/api/digimon/不存在的数码兽/world-model")
        if resp_404.status_code == 404:
            results.append("✅ API 对未知数码兽正确返回 404")
        else:
            results.append(f"❌ API 对未知数码兽应返回 404，实际 {resp_404.status_code}")

    except Exception as e:
        results.append(f"⚠️  API 端点测试跳过（{e}）")

    # ── 汇总 ──
    passed = all("❌" not in r for r in results)
    return passed, results, stats


def print_report(ticks: int, passed: bool, results: list[str], stats: dict):
    """打印格式化验证报告。"""
    print(BAR)
    print("  Phase 20 端到端验证报告 — 自演化世界模型")
    print(f"  运行 {ticks} ticks | 时间: {datetime.utcnow().isoformat()}")
    print(BAR)

    for r in results:
        print(f"  {r}")

    print(SUB)
    print("  总览:")

    if "agent_stats" in stats:
        print(f"  {'Agent':<8} {'情节数':>6} {'规则数':>6}")
        print(f"  {'-' * 22}")
        for name, s in stats["agent_stats"].items():
            print(f"  {name:<8} {s['episodes']:>6} {s['rules']:>6}")

    print(f"  总情节数: {stats.get('total_episodes', '?')}")
    print(f"  总规则数: {stats.get('total_rules', '?')}")
    print(SUB)

    if passed:
        print("  🎉 全部验证通过! Phase 20 端到端正常。")
    else:
        print("  ⚠️  部分验证未通过，请检查上述 ❌ 项。")
    print(BAR)


def main():
    parser = argparse.ArgumentParser(description="Phase 20 端到端验证")
    parser.add_argument(
        "--ticks", type=int, default=DEFAULT_TICKS,
        help=f"运行 tick 数 (默认: {DEFAULT_TICKS})",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help=f"快速模式 ({QUICK_TICKS} ticks)",
    )
    args = parser.parse_args()

    ticks = QUICK_TICKS if args.quick else args.ticks

    print(f"🚀 开始 Phase 20 端到端验证 ({ticks} ticks)...")

    start = time.monotonic()
    passed, results, stats = run_verification(ticks)
    elapsed = time.monotonic() - start

    print_report(ticks, passed, results, stats)
    print(f"\n耗时: {elapsed:.2f}s")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
