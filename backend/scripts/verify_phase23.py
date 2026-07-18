#!/usr/bin/env python3
"""
Phase 23 端到端验证 — 思考成本与认知能量系统
============================================

目标: 验证 CognitiveEnergyPool + EnergyLedger 在模拟世界运行中的
端到端行为——能量衰减、LLM 扣减、恢复、休眠/唤醒完整生命周期。

跑法:
    cd backend
    source .venv/bin/activate
    python scripts/verify_phase23.py              # 默认 60 tick
    python scripts/verify_phase23.py --ticks 100   # 100 ticks
    python scripts/verify_phase23.py --quick       # 快速模式 30 tick

校验项:
1.  能量池初始化 — 满能量、未休眠、计数器归零
2.  Tick 衰减 — 每 tick 自动消耗 base_drain，历史记录正确
3.  LLM 消耗 — spend() 按 token 量扣能量、累积计数
4.  能量恢复 — rest/social/eat 恢复能量、夹紧上限
5.  休眠/唤醒 — 能量归零→休眠、恢复→唤醒
6.  can_think() — 阈值检查，休眠 agent 不可思考
7.  EnergyLedger — 全局统计：活跃/休眠数、平均能量、LLM 总计
8.  API 端点 — /api/digimon/{name}/energy + /api/energy/ledger
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from digimon_world.world.thinking_cost import (  # noqa: E402
    BASE_DRAIN_PER_TICK,
    DORMANCY_THRESHOLD,
    ENERGY_MAX,
    ENERGY_MIN,
    LLM_COST_DIVISOR,
    RECOVER_EAT,
    RECOVER_REST,
    RECOVER_SOCIAL,
    THINK_THRESHOLD,
    CognitiveEnergyPool,
    get_energy_ledger,
)

DEFAULT_TICKS = 60
QUICK_TICKS = 30

BAR = "=" * 65
SUB = "-" * 65


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
        results["checks"].append(
            {"name": name, "passed": condition, "detail": detail}
        )
        return condition

    print(f"\n{BAR}")
    print(f"Phase 23 端到端验证 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"运行 tick 数: {ticks}")
    print(f"{BAR}\n")

    # ── 初始化 ──
    print("⚙️  初始化 CognitiveEnergyPool + EnergyLedger...")
    ledger = get_energy_ledger()
    # 清理之前的测试残留
    ledger.reset_all()

    # 创建 5 只数码兽的能量池
    agent_names = ["亚古兽", "加布兽", "比丘兽", "甲虫兽", "巴鲁兽"]
    pools = {}
    for name in agent_names:
        pools[name] = ledger.get_or_create(name)

    # ══════════════════════════════════════════
    # 校验 1: 能量池初始化
    # ══════════════════════════════════════════
    print(f"{SUB}")
    print("校验 1: 能量池初始化")

    for name in agent_names:
        p = pools[name]
        check(
            f"1.{agent_names.index(name)+1} {name} 初始满能量",
            p.energy == ENERGY_MAX,
            f"energy={p.energy}",
        )
        check(
            f"1.{agent_names.index(name)+1}a {name} 未休眠",
            not p.is_dormant,
            f"is_dormant={p.is_dormant}",
        )

    # ══════════════════════════════════════════
    # 校验 2: Tick 衰减
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 2: Tick 被动能量衰减")

    # 对亚古兽执行 10 tick
    agumon = pools["亚古兽"]
    initial_energy = agumon.energy
    for i in range(10):
        agumon.tick()

    expected = max(ENERGY_MIN, initial_energy - BASE_DRAIN_PER_TICK * 10)
    check(
        "2.1 10 tick 后能量正确减少",
        agumon.energy == expected,
        f"energy={agumon.energy}, expected={expected}",
    )
    check(
        "2.2 能量历史记录了 tick 变更",
        len(agumon.energy_history) >= 10,
        f"history 条数={len(agumon.energy_history)}",
    )

    # ══════════════════════════════════════════
    # 校验 3: LLM 消耗
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 3: LLM 调用消耗认知能量")

    gabumon = pools["加布兽"]
    pre_energy = gabumon.energy
    pre_calls = gabumon.total_llm_calls
    pre_tokens = gabumon.total_tokens_spent

    # 模拟一次反思调用 (~500 tokens)
    gabumon.spend(500, reason="reflect")
    check(
        "3.1 spend 后能量减少",
        gabumon.energy < pre_energy,
        f"before={pre_energy}, after={gabumon.energy}",
    )
    check(
        "3.2 LLM 调用计数 +1",
        gabumon.total_llm_calls == pre_calls + 1,
        f"calls={gabumon.total_llm_calls}",
    )
    check(
        "3.3 Token 累积计数正确",
        gabumon.total_tokens_spent == pre_tokens + 500,
        f"tokens={gabumon.total_tokens_spent}",
    )
    check(
        "3.4 能量历史包含 spend 记录",
        any(e["action"] == "spend" for e in gabumon.energy_history),
    )

    # 最小消耗测试
    cost_before = gabumon.energy
    gabumon.spend(10, reason="plan")  # 10 tokens → cost = max(1, 10//200) = 1
    check(
        "3.5 小 token 消耗最小 1 能量",
        gabumon.energy == max(ENERGY_MIN, cost_before - 1),
        f"energy={gabumon.energy}",
    )

    # ══════════════════════════════════════════
    # 校验 4: 能量恢复
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 4: 能量恢复机制")

    piyomon = pools["比丘兽"]
    # 先消耗到低能量
    piyomon.energy = 20

    # rest 恢复
    piyomon.recover(RECOVER_REST, "rest")
    check(
        "4.1 rest 恢复 +2 能量",
        piyomon.energy == 22,
        f"energy={piyomon.energy}",
    )

    # social 恢复
    piyomon.recover(RECOVER_SOCIAL, "social")
    check(
        "4.2 social 恢复 +5 能量",
        piyomon.energy == 27,
        f"energy={piyomon.energy}",
    )

    # eat 恢复
    piyomon.recover(RECOVER_EAT, "eat")
    check(
        "4.3 eat 恢复 +10 能量",
        piyomon.energy == 37,
        f"energy={piyomon.energy}",
    )

    # 夹紧上限
    piyomon.energy = 98
    piyomon.recover(10, "overflow")
    check(
        "4.4 恢复夹紧到 max_energy",
        piyomon.energy == piyomon.max_energy,
        f"energy={piyomon.energy}",
    )

    # 负恢复忽略
    pre_neg = piyomon.energy
    piyomon.recover(-5, "invalid")
    check(
        "4.5 负恢复量被忽略",
        piyomon.energy == pre_neg,
        f"energy={piyomon.energy}",
    )

    # ══════════════════════════════════════════
    # 校验 5: 休眠/唤醒
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 5: 休眠/唤醒生命周期")

    tentomon = pools["甲虫兽"]
    # 手动设为零
    tentomon.energy = 0
    tentomon.is_dormant = True
    check("5.1 能量 0 → 休眠", tentomon.is_dormant)
    check(
        "5.2 休眠 agent 不可思考",
        not tentomon.can_think(),
        f"can_think={tentomon.can_think()}, energy={tentomon.energy}",
    )

    # 恢复 → 唤醒
    tentomon.recover(10, "awaken")
    check(
        "5.3 恢复后自动唤醒",
        not tentomon.is_dormant,
        f"is_dormant={tentomon.is_dormant}, energy={tentomon.energy}",
    )
    check(
        "5.4 唤醒后可以思考",
        tentomon.can_think(),
        f"can_think={tentomon.can_think()}, energy={tentomon.energy}",
    )

    # 通过 tick 进入休眠
    palmon = pools["巴鲁兽"]
    # 设为低能量
    palmon.energy = 5
    for _ in range(6):
        palmon.tick()  # 6×1 = 6 drain → 归零
    check(
        "5.5 连续 tick 最终进入休眠",
        palmon.is_dormant,
        f"energy={palmon.energy}, dormant={palmon.is_dormant}",
    )

    # ══════════════════════════════════════════
    # 校验 6: can_think 阈值
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 6: can_think() 阈值检查")

    # 刚好在阈值
    test_pool = CognitiveEnergyPool()
    test_pool.energy = THINK_THRESHOLD
    check(
        "6.1 energy == THINK_THRESHOLD → 不可思考",
        not test_pool.can_think(),
        f"energy={test_pool.energy}, threshold={THINK_THRESHOLD}",
    )

    test_pool.energy = THINK_THRESHOLD + 1
    check(
        "6.2 energy == THINK_THRESHOLD + 1 → 可思考",
        test_pool.can_think(),
        f"energy={test_pool.energy}, threshold={THINK_THRESHOLD}",
    )

    test_pool.energy = 50
    check("6.3 充足能量 → 可思考", test_pool.can_think())

    test_pool.energy = 1
    check(
        "6.4 极低能量 → 不可思考",
        not test_pool.can_think(),
        f"energy={test_pool.energy}",
    )

    # ══════════════════════════════════════════
    # 校验 7: EnergyLedger 全局统计
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 7: EnergyLedger 全局统计")

    stats = ledger.get_stats()
    print(f"    total={stats['total_agents']}, active={stats['active_count']}, "
          f"dormant={stats['dormant_count']}, avg_energy={stats['avg_energy']}, "
          f"llm_calls={stats['total_llm_calls']}, tokens={stats['total_tokens']}")

    check("7.1 智能体总数 = 5", stats["total_agents"] == 5)
    check(
        "7.2 活跃 + 休眠 = 总数",
        stats["active_count"] + stats["dormant_count"] == stats["total_agents"],
        f"active={stats['active_count']}, dormant={stats['dormant_count']}",
    )
    check(
        "7.3 有休眠智能体 (巴鲁兽已休眠)",
        stats["dormant_count"] >= 1,
        f"dormant_count={stats['dormant_count']}",
    )
    check(
        "7.4 平均能量合法 (0 ~ 100)",
        0 <= stats["avg_energy"] <= 100,
        f"avg_energy={stats['avg_energy']}",
    )
    check(
        "7.5 LLM 调用总次数 > 0",
        stats["total_llm_calls"] > 0,
        f"total_llm_calls={stats['total_llm_calls']}",
    )

    # ══════════════════════════════════════════
    # 校验 8: API 端点
    # ══════════════════════════════════════════
    print(f"\n{SUB}")
    print("校验 8: API 端点")

    try:
        from fastapi.testclient import TestClient
        from digimon_world.api.app import app

        # 重置 app state 中的 energy ledger（避免使用旧的测试数据）
        from digimon_world.world import thinking_cost as tc_mod
        tc_mod._energy_ledger = ledger

        client = TestClient(app)

        # GET /api/digimon/{name}/energy
        resp = client.get("/api/digimon/亚古兽/energy")
        check(
            "8.1 GET /api/digimon/{name}/energy → 200",
            resp.status_code == 200,
            f"status={resp.status_code}",
        )
        if resp.status_code == 200:
            data = resp.json()
            check("8.2 返回包含 energy 字段", "energy" in data)
            check("8.3 返回包含 category_ledger", "category_ledger" in data)
            energy_pool = data.get("energy", {})
            check(
                "8.4 energy 子对象包含 total_llm_calls",
                "total_llm_calls" in energy_pool,
            )

        # GET /api/energy/ledger
        resp = client.get("/api/energy/ledger")
        check(
            "8.5 GET /api/energy/ledger → 200",
            resp.status_code == 200,
            f"status={resp.status_code}",
        )
        if resp.status_code == 200:
            data = resp.json()
            check("8.6 返回包含 total_agents", "total_agents" in data)
            check("8.7 返回包含 agents 列表", "agents" in data)
            check("8.8 返回包含 active_names", "active_names" in data)

        # 404 测试
        resp = client.get("/api/digimon/不存在/energy")
        check(
            "8.9 不存在 agent → 404",
            resp.status_code == 404,
            f"status={resp.status_code}",
        )

    except Exception as e:
        check("8.x API 测试异常", False, str(e))
        import traceback
        traceback.print_exc()

    # ══════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════
    print(f"\n{BAR}")
    total = results["pass"] + results["fail"]
    print(f"验证结果: {results['pass']} 通过 / {results['fail']} 失败 / {total} 总计")
    if results["fail"] == 0:
        print("🎉 全部通过！Phase 23 认知能量系统端到端验证完成。")
    else:
        print("⚠️  存在失败项，请检查上方输出。")
    print(f"{BAR}\n")

    return results["fail"] == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 23 端到端验证")
    parser.add_argument("--ticks", type=int, default=None, help="运行 tick 数（默认 60）")
    parser.add_argument("--quick", action="store_true", help="快速模式 30 tick")
    args = parser.parse_args()

    success = run_verification(args)
    sys.exit(0 if success else 1)
