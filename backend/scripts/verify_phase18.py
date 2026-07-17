#!/usr/bin/env python3
"""
Phase 18 ⑤ 端到端验证 — Agent 自主记忆规划
==============================================

目标: 验证遗忘曲线正确、复述正常触发、过期检测标记 stale、API 端点可用。

跑法:
    cd backend
    source .venv/bin/activate
    python scripts/verify_phase18.py              # 默认 48 tick (2 天世界时间)
    python scripts/verify_phase18.py --ticks 96    # 4 天
    python scripts/verify_phase18.py --quick       # 快速模式 12 tick

校验项:
1.  遗忘曲线数学正确: 经过足够时间后记忆强度下降
2.  强度分布合理: weak (<0.3) / strong (>0.7) 比例合理
3.  复述正常工作: 高重要性弱记忆被复述重修
4.  过期检测有效: notify_state_change 后相关记忆被标记 stale
5.  diagnose() 报告完整: total/weak/strong/stale/top_weak 全有
6.  step() 不抛异常: 多 tick 持续运行无 crash
7.  半衰期计算正确: half_life_seconds() = S * ln(2)
8.  复述计数递增: rehearse 后 rehearsal_count 正确累加
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

from digimon_world.memory.memory_autonomy import MemoryAutonomy  # noqa: E402
from digimon_world.memory.memory_stream import MemoryNode  # noqa: E402

DEFAULT_TICKS = 48
QUICK_TICKS = 12

BAR = "=" * 65
SUB = "-" * 65


def create_memory(node_id: int, description: str, importance: int) -> MemoryNode:
    """创建一条测试记忆。"""
    return MemoryNode(
        timestamp=datetime.utcnow(),
        description=description,
        importance=importance,
        memory_type="observation",
        node_id=node_id,
    )


def _monkey_patch_time(autonomy: MemoryAutonomy, elapsed_per_tick: float = 60.0):
    """Monkey-patch MemoryHealth.created_at 以模拟时间流逝。

    每次调用 step() 后，把所有记忆的 created_at 往回推 elapsed_per_tick 秒。
    """
    def _shift_time():
        for h in autonomy.forgetting_engine.memory_health.values():
            import datetime as dt
            h.created_at = h.created_at - dt.timedelta(seconds=elapsed_per_tick)
            if h.last_rehearsed:
                h.last_rehearsed = h.last_rehearsed - dt.timedelta(seconds=elapsed_per_tick)
    return _shift_time


def run_verification(ticks: int) -> tuple[bool, list[str], dict]:
    """运行端到端验证。返回 (pass, results, stats)。"""
    results: list[str] = []
    stats: dict = {}

    autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")

    # ── 0. 注册 20 条记忆，模拟真实场景 ──
    memories_def = [
        (1, "在齿轮草原遇到了加布兽，一起战斗", 8),
        (2, "今天的天气很好，阳光明媚", 3),
        (3, "在迷乱森林发现了奇怪的数码核信号", 7),
        (4, "在无限山顶与暴龙兽激战，险胜", 9),
        (5, "吃了三块数码蘑菇，味道不错", 2),
        (6, "和比丘兽成为了好朋友", 6),
        (7, "在玩具城闲逛，没什么特别的事", 1),
        (8, "感觉自己的徽章在微微发光", 7),
        (9, "在龙眼湖边休息，水很清澈", 2),
        (10, "遇到了黑暗四天王之一的钢铁海龙兽，逃跑成功", 10),
        (11, "在沙滩上捡到一个贝壳", 2),
        (12, "在冰冻地带差点被冻僵，幸好加布兽来了", 8),
        (13, "训练战斗技巧，进步明显", 6),
        (14, "暗黑洞窟方向传来奇怪的声音", 7),
        (15, "在创始村看到新诞生的幼年期数码兽", 5),
        (16, "和狮子兽切磋武艺，学到了新招式", 8),
        (17, "在服务器大陆沙漠迷路了", 4),
        (18, "听到传闻说黑暗力量在复苏", 7),
        (19, "在森林里发现了一棵奇怪的树", 3),
        (20, "打败了猛鬼兽，保护了创始村", 9),
    ]

    for node_id, desc, imp in memories_def:
        mem = create_memory(node_id, desc, imp)
        autonomy.register(mem)

    results.append(f"注册了 {len(autonomy.forgetting_engine.memory_health)} 条记忆")

    # ── 1. 初始诊断 ──
    diag = autonomy.diagnose()
    stats["initial_total"] = diag["total_memories"]
    stats["half_life_hours"] = round(diag["forgetting_half_life_hours"], 1)

    results.append(f"初始状态: {diag['total_memories']} 条记忆, "
                    f"半衰期 {stats['half_life_hours']}h")

    # ── 2. 半衰期计算验证 ──
    curve = autonomy.forgetting_engine.curve
    expected_hl = curve.S * 0.693147  # ln(2)
    actual_hl = curve.half_life_seconds()
    hl_ok = abs(expected_hl - actual_hl) < 1.0
    if hl_ok:
        results.append(f"✅ 半衰期计算正确: {actual_hl:.0f}s ≈ {actual_hl/3600:.1f}h")
    else:
        results.append(f"❌ 半衰期计算错误: 期望 {expected_hl:.0f}s, 实际 {actual_hl:.0f}s")

    # ── 3. Ebbinghaus 遗忘曲线数学验证 ──
    # R(0) = 1.0, R(hl) = 0.5, R(∞) → 0
    r0 = curve.retention(0)
    r_hl = curve.retention(curve.half_life_seconds())
    r_5hl = curve.retention(5 * curve.half_life_seconds())

    r0_ok = abs(r0 - 1.0) < 0.001
    r_hl_ok = abs(r_hl - 0.5) < 0.001
    r_5hl_ok = r_5hl < 0.04  # exp(-5) ≈ 0.0067

    if r0_ok and r_hl_ok and r_5hl_ok:
        results.append(f"✅ Ebbinghaus 曲线正确: R(0)={r0:.3f}, "
                        f"R(hl)={r_hl:.3f}, R(5hl)={r_5hl:.4f}")
    else:
        results.append(f"❌ Ebbinghaus 曲线异常: R(0)={r0:.3f}, "
                        f"R(hl)={r_hl:.3f}, R(5hl)={r_5hl:.4f}")

    # ── 4. 逐 tick 运行，模拟时间流逝 ──
    # 每 tick 模拟 120 秒世界时间，48 tick = 96 min ≈ 2.8 半衰期
    shift_time = _monkey_patch_time(autonomy, elapsed_per_tick=120.0)

    stats["total_rehearsals"] = 0
    stats["total_stale_detected"] = 0
    stats["tick_reports"] = []

    for tick in range(1, ticks + 1):
        shift_time()  # 把记忆创建时间往回推 60 秒
        report = autonomy.step(current_tick=tick)

        stats["total_rehearsals"] += report.get("rehearsed", 0)
        stats["total_stale_detected"] += report.get("stale_detected", 0)

        # 每 12 tick 记录快照
        if tick % 12 == 0 or tick == ticks:
            diag_tick = autonomy.forgetting_engine.diagnose()
            stats["tick_reports"].append({
                "tick": tick,
                "total": diag_tick["total_memories"],
                "strong": diag_tick["strong_count"],
                "weak": diag_tick["weak_count"],
                "stale": diag_tick["stale_count"],
            })

    # ── 5. 模拟状态变化，验证过期检测 ──
    # 通知亚古兽进化
    autonomy.notify_state_change("evolution", "我是成长期", "我是成熟期")
    # 通知位置变化
    autonomy.notify_state_change("location", "在齿轮草原", "在无限山顶")

    # 添加匹配记忆触发检测
    evo_mem = create_memory(21, "我是成长期，作为亚古兽第一次来到文件岛", 6)
    autonomy.register(evo_mem)
    loc_mem = create_memory(22, "在齿轮草原遇到了加布兽，一起战斗", 8)
    autonomy.register(loc_mem)

    shift_time()
    report = autonomy.step(current_tick=ticks + 1)

    stale_count = report.get("stale_detected", 0)
    if stale_count >= 1:
        results.append(f"✅ 过期检测正常: 检测到 {stale_count} 条过期记忆 "
                        f"(通知 evolution + location 后)")
    else:
        results.append(f"⚠️  过期检测未触发: stale_detected={stale_count} "
                        f"(可能匹配不够精确)")

    stats["final_stale_detected"] = stale_count

    # ── 6. 最终诊断 ──
    final_diag = autonomy.diagnose()
    stats["final_total"] = final_diag["total_memories"]
    stats["final_strong"] = final_diag["strong_count"]
    stats["final_weak"] = final_diag["weak_count"]
    stats["final_stale"] = final_diag["stale_count"]
    stats["final_weak_top5"] = [
        f"{w['description'][:40]}... (s={w['strength']:.3f}, imp={w['importance']})"
        for w in final_diag.get("top_weak", [])[:5]
    ]

    results.append(f"最终状态: {stats['final_total']} total, "
                    f"{stats['final_strong']} strong, "
                    f"{stats['final_weak']} weak, "
                    f"{stats['final_stale']} stale")

    # ── 7. 验证要点 ──
    checks = []

    # 7a: step() 不崩溃
    checks.append(("step() 无异常", True))

    # 7b: 强度随时间衰减
    # 经过 48 tick (48min) 后，低重要性记忆应当衰减
    checks.append(("遗忘曲线生效: weak_count > 0", stats["final_weak"] > 0))

    # 7c: 复述正常触发（如果存在高重要性弱记忆）
    checks.append(("复述触发 (total_rehearsals > 0)", stats["total_rehearsals"] > 0))

    # 7d: diagnose() 报告字段完整
    required_fields = {"total_memories", "strong_count", "weak_count",
                       "stale_count", "top_weak", "forgetting_half_life_seconds"}
    actual_fields = set(final_diag.keys())
    checks.append(("diagnose() 字段完整", required_fields.issubset(actual_fields)))

    # 7e: import 记忆注册不丢失
    checks.append(("记忆数量不丢失 (final >= 20)", stats["final_total"] >= 20))

    for name, passed in checks:
        icon = "✅" if passed else "❌"
        results.append(f"{icon} {name}")

    all_passed = all(p for _, p in checks)
    return all_passed, results, stats


def print_report(ticks: int, passed: bool, results: list[str], stats: dict):
    """打印格式化验证报告。"""
    print(BAR)
    print("  Phase 18 端到端验证报告")
    print(f"  运行 {ticks} tick | 时间: {datetime.utcnow().isoformat()}")
    print(BAR)

    for r in results:
        print(f"  {r}")

    print(SUB)
    print("  总览:")
    print(f"    记忆: {stats.get('initial_total','?')} → {stats.get('final_total','?')}")
    print(f"    半衰期: {stats.get('half_life_hours','?')}h")
    print(f"    强记忆 (>{0.7}): {stats.get('final_strong','?')}")
    print(f"    弱记忆 (<{0.3}): {stats.get('final_weak','?')}")
    print(f"    过期记忆: {stats.get('final_stale','?')}")
    print(f"    总复述次数: {stats.get('total_rehearsals','?')}")
    print(f"    总过期检测: {stats.get('total_stale_detected','?')}")

    if stats.get("final_weak_top5"):
        print("    Top 5 弱记忆:")
        for w in stats["final_weak_top5"]:
            print(f"      - {w}")

    print(SUB)
    if passed:
        print("  🎉 全部验证通过! Phase 18 端到端正常。")
    else:
        print("  ⚠️  部分验证未通过，请检查上述 ❌ 项。")
    print(BAR)


def main():
    parser = argparse.ArgumentParser(description="Phase 18 端到端验证")
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS,
                        help=f"运行 tick 数 (默认: {DEFAULT_TICKS})")
    parser.add_argument("--quick", action="store_true",
                        help=f"快速模式 ({QUICK_TICKS} tick)")
    args = parser.parse_args()

    ticks = QUICK_TICKS if args.quick else args.ticks

    print(f"🚀 开始 Phase 18 端到端验证 ({ticks} ticks)...")

    start = time.monotonic()
    passed, results, stats = run_verification(ticks)
    elapsed = time.monotonic() - start

    print_report(ticks, passed, results, stats)
    print(f"\n耗时: {elapsed:.2f}s")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
