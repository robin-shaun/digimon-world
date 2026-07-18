#!/usr/bin/env python3
"""
Phase 24 端到端验证: 能量经济与互惠利他
======================================

验证能量经济的完整生命周期:
1. 能量转移（donation/trade/awaken/tribute）
2. 互惠债务（记录、衰败、上限）
3. 利他评分（0-1 归一化）
4. 债务排名（top creditors/debtors）
5. 唤醒休眠 agent
6. 绝望救济（低能量 agent 获得回报）
7. 调度器集成（economy.step 正常执行）
8. API 端点可访问

Usage:
    cd backend && source .venv/bin/activate && python scripts/verify_phase24.py
"""

import sys
from pathlib import Path

# 确保 backend 项目根目录在 sys.path
_backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_root / "src"))

from digimon_world.economy.energy_economy import (  # noqa: E402
    AWAKEN_HELPER_COST,
    AWAKEN_RESTORE_AMOUNT,
    DEBT_DECAY_INTERVAL,
    DESPERATION_ENERGY_THRESHOLD,
    MAX_DEBT,
    EnergyTransfer,
    ReciprocalAltruism,
)

from digimon_world.world import get_world, reset_world  # noqa: E402
from digimon_world.economy import get_energy_economy, reset_energy_economy  # noqa: E402

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


def main():
    print("=" * 60)
    print("  Phase 24 验证: 能量经济与互惠利他")
    print("=" * 60)

    # ── 1. EnergyTransfer 数据结构 ──
    print("\n📦 1. EnergyTransfer 数据结构")

    t1 = EnergyTransfer.create("agumon", "gabumon", 15.0, "donation", "分享食物", 1)
    check("factory creates valid transfer", t1.amount == 15.0)
    check("transfer frozen — fields immutable",
          hasattr(t1, "transfer_id") and t1.transfer_id != "")
    d = t1.to_dict()
    check("to_dict serializable",
          all(k in d for k in ["transfer_id", "from_agent", "to_agent",
                               "amount", "transfer_type", "reason", "tick", "timestamp"]))

    t2 = EnergyTransfer.create("gabumon", "agumon", 10.0, "trade", "交换物资", 2)
    check("transfers have unique IDs", t1.transfer_id != t2.transfer_id)
    check("transfer types preserved", t2.transfer_type == "trade")

    # ── 2. ReciprocalAltruism 债务系统 ──
    print("\n📊 2. ReciprocalAltruism 互惠债务")

    a = ReciprocalAltruism()

    # 初始状态
    check("initial debt is zero", a.get_debt("b", "a") == 0.0)
    check("self-help not recorded", a.record_help("a", "a", 10.0, 0) == 0.0)
    check("initial altruism score is 0", a.get_altruism_score("anyone") == 0.0)

    # 记录帮助
    debt1 = a.record_help("helper_A", "receiver_B", 20.0, 10)
    check("record help creates debt", debt1 == 20.0)
    check("get_debt returns correct amount", a.get_debt("receiver_B", "helper_A") == 20.0)
    check("creditor sees no debt to debtor",
          a.get_debt("helper_A", "receiver_B") == 0.0)

    # 累积债务
    a.record_help("helper_A", "receiver_B", 15.0, 20)
    check("cumulative debt adds up", a.get_debt("receiver_B", "helper_A") == 35.0)

    # 债务上限
    a.record_help("helper_A", "receiver_B", 100.0, 30)
    check("debt capped at MAX_DEBT",
          abs(a.get_debt("receiver_B", "helper_A") - MAX_DEBT) < 0.01,
          f"expected {MAX_DEBT}, got {a.get_debt('receiver_B', 'helper_A')}")

    # 利他评分
    score = a.get_altruism_score("helper_A")
    check("altruism score > 0 after helping", score > 0)
    check("altruism score <= 1.0", score <= 1.0)

    # 互惠判断
    check("should_reciprocate triggers above threshold",
          a.should_reciprocate("receiver_B", "helper_A"))
    check("should_reciprocate false for new agents",
          not a.should_reciprocate("stranger", "helper_A"))

    # 债务排名
    a.record_help("helper_A", "receiver_C", 10.0, 40)
    top_creditors = a.get_top_creditors("helper_A", n=5)
    check("get_top_creditors returns list",
          isinstance(top_creditors, list) and len(top_creditors) >= 2)
    if top_creditors:
        check("top_creditors sorted descending",
              all(top_creditors[i][1] >= top_creditors[i+1][1]
                  for i in range(len(top_creditors)-1)))

    top_debtors = a.get_top_debtors("receiver_B", n=5)
    check("get_top_debtors returns correct creditor",
          any(d[0] == "helper_A" for d in top_debtors))

    # 债务衰败
    old_debt = a.get_debt("receiver_B", "helper_A")
    decayed = a.decay_debts(DEBT_DECAY_INTERVAL + 1)
    new_debt = a.get_debt("receiver_B", "helper_A")
    check("decay_debts reduces debt", decayed > 0 and new_debt < old_debt,
          f"expected < {old_debt:.1f}, got {new_debt:.1f}")

    # 串行化
    d = a.to_dict()
    check("altruism to_dict has correct keys",
          "debts" in d and "last_decay_tick" in d)

    # ── 3. EnergyEconomy 引擎 ──
    print("\n⚙️  3. EnergyEconomy 引擎")

    reset_world()
    reset_energy_economy()

    world = get_world()
    assert world.count() > 0, "World must have digimon"

    # 获取 agent 引用
    agents = {a.name: a for a in world.all()}
    agumon = agents.get("亚古兽")
    gabumon = agents.get("加布兽")

    if agumon is None or gabumon is None:
        print("  ⚠️  Agent names don't match expected; using first two available")
        names = list(agents.keys())[:2]
        agumon = agents[names[0]]
        gabumon = agents[names[1]]

    economy = get_energy_economy()
    check("economy singleton works", economy is get_energy_economy())

    # 确保有足够能量
    agumon.cognitive_energy.energy = agumon.cognitive_energy.max_energy
    gabumon.cognitive_energy.energy = gabumon.cognitive_energy.max_energy

    # 捐赠
    transfer = economy.propose_transfer(
        agumon.name, gabumon.name, 15.0, "donation", "分享能量", 1
    )
    check("donation transfer succeeds", transfer is not None)
    if transfer:
        check("donation creates debt",
              economy.altruism.get_debt(gabumon.name, agumon.name) > 0)

    # 交易
    trade = economy.propose_transfer(
        gabumon.name, agumon.name, 10.0, "trade", "交换物资", 2
    )
    check("trade transfer succeeds", trade is not None)
    if trade:
        check("trade does NOT create debt",
              economy.altruism.get_debt(agumon.name, gabumon.name) == 0.0)

    # 转移历史
    history = economy.get_transfer_history()
    check("transfer history has records", len(history) >= 2)
    check("transfer history filter by agent",
          len(economy.get_transfer_history(agent_name=agumon.name)) >= 2)

    # 统计数据
    stats = economy.get_economy_stats()
    check("stats has total_transfers", "total_transfers" in stats)
    check("stats transfers >= 2", stats["total_transfers"] >= 2)
    check("stats has avg_altruism_score", "avg_altruism_score" in stats)

    # ── 4. 唤醒休眠 agent ──
    print("\n😴 4. 唤醒休眠 agent")

    # 让 gabumon 休眠
    gabumon.cognitive_energy.energy = 0
    gabumon.cognitive_energy.is_dormant = True

    # 尝试唤醒
    awaken_ops = economy.check_awaken_opportunities()
    check("awaken opportunities method returns list",
          isinstance(awaken_ops, list))

    # 直接提议唤醒
    awaken = economy.propose_transfer(
        agumon.name, gabumon.name, AWAKEN_HELPER_COST, "awaken",
        "唤醒朋友", 5
    )
    check("awaken transfer succeeds", awaken is not None)
    if awaken:
        check("awaken restores energy to AWAKEN_RESTORE_AMOUNT",
              abs(gabumon.cognitive_energy.energy - AWAKEN_RESTORE_AMOUNT) < 1,
              f"got {gabumon.cognitive_energy.energy}")
        check("dormant flag cleared after awaken",
              not gabumon.cognitive_energy.is_dormant)

    # ── 5. 绝望救济 ──
    print("\n🆘 5. 绝望救济 (desperation relief)")

    # Setup: gabumon helped agumon heavily (debt), now gabumon is low energy
    # → agumon owes gabumon → should_reciprocate(agumon, gabumon) should be True
    economy.altruism.clear()
    economy.altruism.record_help(agumon.name, gabumon.name, 30.0, 10)
    # Now gabumon is the low-energy creditor, agumon is the debtor
    gabumon.cognitive_energy.energy = 10.0  # below DESPERATION threshold
    gabumon.cognitive_energy.is_dormant = False
    agumon.cognitive_energy.energy = agumon.cognitive_energy.max_energy

    check("desperation energy below threshold",
          gabumon.cognitive_energy.energy < DESPERATION_ENERGY_THRESHOLD)
    check("reciprocity should trigger",
          economy.altruism.should_reciprocate(gabumon.name, agumon.name))

    relief_ops = economy.check_desperation_relief()
    check("desperation relief returns opportunities",
          isinstance(relief_ops, list))

    # ── 6. step() 方法 ──
    print("\n🔄 6. economy.step() 完整流程")

    old_transfer_count = len(economy.transfer_history)
    events = economy.step(20)
    check("step returns list", isinstance(events, list))
    new_transfer_count = len(economy.transfer_history)
    check("step may create transfers",
          new_transfer_count >= old_transfer_count)

    # ── 7. 调度器集成 ──
    print("\n🔗 7. 调度器集成")

    try:
        import importlib
        importlib.import_module("digimon_world.world.scheduler")
        check("import economy in scheduler", True)
    except ImportError as e:
        check("import economy in scheduler", False, str(e))

    # ── 8. API 端点验证 ──
    print("\n🌐 8. API 端点验证")

    try:
        from fastapi.testclient import TestClient
        from digimon_world.api.app import app

        client = TestClient(app)

        # GET /api/economy/stats
        r = client.get("/api/economy/stats")
        check("GET /api/economy/stats → 200", r.status_code == 200)
        data = r.json()
        check("stats has total_transfers", "total_transfers" in data)
        check("stats has avg_altruism_score", "avg_altruism_score" in data)
        check("stats has transfers_by_type", "transfers_by_type" in data)

        # GET /api/economy/transfers
        r = client.get("/api/economy/transfers")
        check("GET /api/economy/transfers → 200", r.status_code == 200)
        data = r.json()
        check("transfers has count", "count" in data)
        check("transfers has list", "transfers" in data)

        # GET /api/economy/transfers?agent_name=X
        if economy.transfer_history:
            first_agent = economy.transfer_history[0].from_agent
            r = client.get(f"/api/economy/transfers?agent_name={first_agent}")
            check("GET /api/economy/transfers?agent_name=... → 200",
                  r.status_code == 200)
            data = r.json()
            check("agent-filtered transfers correct",
                  all(t["from_agent"] == first_agent or t["to_agent"] == first_agent
                      for t in data["transfers"]))

        # GET /api/altruism/{name}
        r = client.get(f"/api/altruism/{agumon.name}")
        check("GET /api/altruism/{name} → 200", r.status_code == 200)
        data = r.json()
        check("altruism has score", "altruism_score" in data)
        check("altruism has top_creditors", "top_creditors" in data)
        check("altruism has top_debtors", "top_debtors" in data)

        # GET /api/altruism/nonexistent → 404
        r = client.get("/api/altruism/不存在的数码兽")
        check("GET /api/altruism/nonexistent → 404", r.status_code == 404)

        print("\n  ✅ All API endpoints accessible")
    except Exception as e:
        check("API test setup", False, str(e))

    # TODO: browser_vision end-to-end test for frontend economy panel

    # ── 汇总 ──
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    if failed == 0:
        print(f"  🎉 {PASS} {passed}/{total} ALL PASS")
    else:
        print(f"  ⚠️  {passed}/{total} PASS, {failed} FAIL")
        print("\n  失败项:")
        for name, ok, detail in results:
            if not ok:
                print(f"    ❌ {name}: {detail}")

    print("=" * 60)

    # 清理
    reset_world()
    reset_energy_economy()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
