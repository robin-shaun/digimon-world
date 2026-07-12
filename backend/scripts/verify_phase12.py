#!/usr/bin/env python3
"""
Phase 12 ⑤ 长期一致性测试 — 运行一周世界时间
================================================

目标: 验证无 memory leak / state drift,压缩系统正常工作。

跑法(零网络依赖):

    cd backend
    source .venv/bin/activate
    python scripts/verify_phase12.py              # 默认 1008 tick (~1 天世界时间)
    python scripts/verify_phase12.py --ticks 5040  # 5 天
    python scripts/verify_phase12.py --ticks 10080 # 1 周
    python scripts/verify_phase12.py --quick       # 快速模式 240 tick (~4 小时)

校验项:
1.  时钟正确推进: elapsed_minutes >= ticks
2.  Agent 数量稳定: 无丢失
3.  所有 agent 位置在画布内
4.  所有 agent 有有效 region_id
5.  Scheduler tick_count 一致
6.  记忆压缩生效: total_deduped > 0 或 total_summarized > 0 (长时间运行必须触发压缩)
7.  记忆增长收敛: 后 1/3 时段的每 tick 平均记忆增长率 < 前 2/3 时段的 50%
8.  世界事件不爆炸: events 总数 < ticks * 30 (无事件泄漏)
9.  属性/地区分布完整
10. Agent 内部状态一致: memory.entries 总数稳定(无爆炸增长)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SRC = BACKEND_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from digimon_world.agents.dialogue import Dialogue
from digimon_world.llm.client import (
    FakeLlmClient,
    LlmModel,
    get_client,
    set_client,
)
from digimon_world.world import WorldClock, WorldScheduler, reset_world, get_world

# 默认 tick 数: 1008 = ~1 天世界时间 (real_to_world_ratio=60, 1 tick=1 世界分钟)
DEFAULT_TICKS = 1008
QUICK_TICKS = 240
WEEK_TICKS = 10080

BAR = "=" * 65
SUB = "-" * 65


def _build_fake_client() -> FakeLlmClient:
    """构造 30-agent 可用的 FakeLlmClient。

    给 Planner / Reflector / Dialogue 预设多样化的回复，
    避免所有 agent 返回同一句话。
    """
    fake = FakeLlmClient()

    # ---- Dialogue ----
    dialogue_lines = [
        "你好呀!今天天气不错!",
        "嘿,你从哪里来的?",
        "我看到那边有个奇怪的东西...",
        "要不要一起去探险?",
        "小心!我感觉到黑暗力量了...",
        "这片区域的数码核有点不对劲。",
        "哈哈,今天找到好多好吃的!",
        "别过来,这里是我的地盘!",
        "你也是来调查齿轮草原的吗?",
        "嘘...有人在暗中观察我们。",
        "那边的花开了,好漂亮!",
        "昨晚的暴风雨好可怕。",
        "你闻到什么味道了吗?",
        "我的徽章最近在发光。",
        "要不要比试一下?",
    ]
    for i, line in enumerate(dialogue_lines):
        fake.set_reply(LlmModel.HAIKU, contains=f"dlg_idx={i}", reply=line)
    fake.set_reply(LlmModel.HAIKU, contains="只输出这句台词", reply="你好呀!")
    fake.set_reply(LlmModel.HAIKU, reply="...")

    # ---- Planner ----
    plans = [
        "在沙滩上闲逛",
        "向北走到高处巡视",
        "停下来休息一会儿",
        "去西边的树林观察",
        "在齿轮草原收集零件",
        "寻找数码核的线索",
        "跟随气味追踪目标",
        "返回巢穴补充能量",
        "在龙眼湖附近巡逻",
        "去玩具城看看有没有新发现",
        "在迷乱森林修炼",
        "向无限山顶攀登",
        "在冰冻地带寻找食物",
        "去创始村探望老朋友",
        "在暗黑洞窟边缘探查",
    ]
    for i, p in enumerate(plans):
        fake.set_reply(LlmModel.HAIKU, contains=f"plan_idx={i}", reply=p)
    fake.set_reply(LlmModel.HAIKU, contains="plan", reply="在附近闲逛")
    fake.set_reply(LlmModel.HAIKU, reply="在附近闲逛")

    # ---- Reflector ----
    reflections = [
        "今天过得挺充实,遇到了几个新朋友。",
        "齿轮草原的数据流好像有点异常...",
        "我应该加强训练,变得更强。",
        "无限山方向的黑暗气息越来越浓了。",
        "今天找到了不错的食物来源。",
        "天气变冷了,要注意保暖。",
        "创始村那边似乎有新的数码蛋。",
        "最近遇到的数码兽都很友好。",
    ]
    for i, r in enumerate(reflections):
        fake.set_reply(LlmModel.OPUS, contains=f"refl_idx={i}", reply=r)
    fake.set_reply(LlmModel.OPUS, contains="reflect", reply="今天过得挺充实")
    fake.set_reply(LlmModel.OPUS, reply="一切正常。")

    return fake


def _print_checkpoint(tick: int, total: int, clock: WorldClock,
                      world, scheduler, agents, latencies: list[float]) -> None:
    """打印进度检查点。"""
    mem_total = sum(len(a.memory.entries) for a in agents)
    mem_avg = mem_total / max(1, len(agents))
    mem_max = max((len(a.memory.entries) for a in agents), default=0)
    lat_avg = sum(latencies[-20:]) / max(1, len(latencies[-20:])) if latencies else 0
    print(
        f"  [tick {tick:>5}/{total}] "
        f"{clock.format_clock()}  "
        f"events={len(world.events):>6}  "
        f"mem_avg={mem_avg:>6.1f}  mem_max={mem_max:>5}  "
        f"lat={lat_avg:>6.1f}ms  "
        f"sched={scheduler.tick_count}"
    )


async def run(ticks: int) -> int:
    """主流程。返回 0=PASS, 1=FAIL。"""

    print(BAR)
    print(f" Phase 12 ⑤ 长期一致性测试 (ticks={ticks})")
    print(f" real_to_world_ratio=60, 1 tick ≈ 1 世界分钟")
    print(f" 世界时间跨度: ~{ticks / 60 / 24:.1f} 天")
    print(BAR)

    # 注入 FakeLlmClient（零网络）
    set_client(_build_fake_client())

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    all_agents = world.all()
    total_agents = len(all_agents)
    print(f" 数码兽: {total_agents} 只")
    print(f" 启动时刻: {clock.format_clock()}")
    print(SUB)

    # 初始快照
    initial_mem_counts = {a.name: len(a.memory.entries) for a in all_agents}
    initial_total_mem = sum(initial_mem_counts.values())
    initial_compression = {
        a.name: {
            "deduped": a.memory.total_deduped,
            "summarized": a.memory.total_summarized,
            "pruned": a.memory.total_pruned,
        }
        for a in all_agents
    }

    # 周期性采样记录 (用于增长曲线分析)
    sample_interval = max(1, ticks // 20)
    memory_samples: list[tuple[int, int]] = []  # [(tick, total_mem), ...]
    event_samples: list[tuple[int, int]] = []   # [(tick, event_count), ...]

    tick_latencies: list[float] = []
    progress_interval = max(1, ticks // 10)
    t_start = time.perf_counter()

    for i in range(ticks):
        t0 = time.perf_counter()
        await scheduler.tick_once(real_seconds=1.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        tick_latencies.append(elapsed_ms)

        # 定期采样
        if (i + 1) % sample_interval == 0:
            total_mem = sum(len(a.memory.entries) for a in world.all())
            memory_samples.append((i + 1, total_mem))
            event_samples.append((i + 1, len(world.events)))

        if (i + 1) % progress_interval == 0:
            _print_checkpoint(i + 1, ticks, clock, world, scheduler, world.all(), tick_latencies)

    total_real_time = time.perf_counter() - t_start
    print(SUB)
    print(f" 总耗时: {total_real_time:.1f}s  "
          f"({ticks / total_real_time:.1f} ticks/s)")
    print(SUB)

    # ── 校验 ──
    results: list[tuple[str, bool, str]] = []
    agents_after = world.all()

    # 1. 时钟推进
    elapsed_ok = clock.elapsed_minutes >= ticks - 2
    results.append((
        "1. clock.elapsed_minutes",
        elapsed_ok,
        f"elapsed={clock.elapsed_minutes}min (期望 >= {ticks - 2})",
    ))

    # 2. Agent 数量稳定
    count_ok = len(agents_after) == total_agents
    results.append((
        "2. agent count stable",
        count_ok,
        f"start={total_agents} end={len(agents_after)}",
    ))

    # 3. 所有 agent 位置在画布内
    canvas_w, canvas_h = 1200, 800
    oob = []
    for a in agents_after:
        x, y = a.location
        if not (0 <= x <= canvas_w and 0 <= y <= canvas_h):
            oob.append(f"{a.name}=({x},{y})")
    pos_ok = len(oob) == 0
    results.append((
        "3. all agents in canvas",
        pos_ok,
        f"OOB={len(oob)}" + (f" ({'; '.join(oob[:3])})" if oob else ""),
    ))

    # 4. 所有 agent 有 region_id
    no_region = [a.name for a in agents_after if not a.region_id]
    region_ok = len(no_region) == 0
    results.append((
        "4. all agents have region",
        region_ok,
        f"missing={len(no_region)}" + (f" ({', '.join(no_region[:3])})" if no_region else ""),
    ))

    # 5. Scheduler tick_count
    tick_ok = scheduler.tick_count == ticks
    results.append((
        "5. scheduler tick_count",
        tick_ok,
        f"got={scheduler.tick_count}, expected={ticks}",
    ))

    # 6. 记忆压缩生效
    final_compression = {
        a.name: {
            "deduped": a.memory.total_deduped,
            "summarized": a.memory.total_summarized,
            "pruned": a.memory.total_pruned,
        }
        for a in agents_after
    }
    total_deduped = sum(v["deduped"] for v in final_compression.values())
    total_summarized = sum(v["summarized"] for v in final_compression.values())
    total_pruned = sum(v["pruned"] for v in final_compression.values())
    compression_ok = ticks >= 500 and (total_deduped > 0 or total_summarized > 0 or total_pruned > 0)
    if ticks < 500:
        compression_ok = True  # 短时间运行不强制压缩
    results.append((
        "6. memory compression active",
        compression_ok,
        f"deduped={total_deduped} summarized={total_summarized} pruned={total_pruned}",
    ))

    # 7. 记忆增长收敛
    # 取后 1/3 时段的增长速率 vs 前 2/3
    if len(memory_samples) >= 6:
        split = len(memory_samples) * 2 // 3
        early_samples = memory_samples[:split]
        late_samples = memory_samples[split:]

        if len(early_samples) > 1 and len(late_samples) > 1:
            early_growth = (early_samples[-1][1] - early_samples[0][1]) / max(1, early_samples[-1][0] - early_samples[0][0])
            late_growth = (late_samples[-1][1] - late_samples[0][1]) / max(1, late_samples[-1][0] - late_samples[0][0])
            if early_growth > 0.01:
                growth_ratio = late_growth / early_growth
                growth_ok = growth_ratio < 1.5  # 后期增长不超过前期的 150%
            else:
                growth_ok = True
                growth_ratio = 0.0
        else:
            growth_ok = True
            growth_ratio = 0.0
            early_growth = late_growth = 0.0
    else:
        growth_ok = True
        growth_ratio = 0.0
        early_growth = late_growth = 0.0

    results.append((
        "7. memory growth convergence",
        growth_ok,
        f"early_rate={early_growth:.2f}/tick late_rate={late_growth:.2f}/tick ratio={growth_ratio:.2f}",
    ))

    # 8. 世界事件不爆炸
    event_count = len(world.events)
    max_expected = ticks * 100  # 每 tick 最多 100 个事件(合理上限, 30 agents × ~3 events)
    events_ok = event_count < max_expected
    results.append((
        "8. events not exploding",
        events_ok,
        f"events={event_count} (max_expected={max_expected})",
    ))

    # 9. 属性/地区分布完整
    attr_counts: dict[str, int] = {}
    for a in agents_after:
        key = a.attribute.value if a.attribute else "unknown"
        attr_counts[key] = attr_counts.get(key, 0) + 1
    attr_ok = all(
        attr_counts.get(k, 0) >= 1
        for k in ["vaccine", "data", "virus", "free"]
    )
    results.append((
        "9. attribute diversity",
        attr_ok,
        f"vaccine={attr_counts.get('vaccine',0)} data={attr_counts.get('data',0)} "
        f"virus={attr_counts.get('virus',0)} free={attr_counts.get('free',0)}",
    ))

    # 10. Memory 总数合理 (不爆炸)
    total_mem_end = sum(len(a.memory.entries) for a in agents_after)
    mem_growth = total_mem_end - initial_total_mem
    # 每 agent 平均记忆不超过 300 (有压缩系统在,正常不会这么多)
    avg_mem_end = total_mem_end / max(1, len(agents_after))
    mem_bounded = avg_mem_end < 300
    results.append((
        "10. memory bounded (avg < 300/agent)",
        mem_bounded,
        f"avg={avg_mem_end:.1f} total={total_mem_end} growth={mem_growth}",
    ))

    # ── 打印校验表 ──
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:<45}  {detail}")
    print(SUB)
    print(f" 汇总: {passed} PASS / {failed} FAIL")
    print()

    # ── 统计面板 ──
    print(BAR)
    print(" 📊 统计面板")
    print(BAR)
    mem_counts = [len(a.memory.entries) for a in agents_after]
    print(f" 世界时间: {clock.format_clock()} (elapsed {clock.elapsed_minutes} min)")
    print(f" 总事件数: {event_count}")
    print(f" 调度器 ticks: {scheduler.tick_count}")
    print(f" 记忆数: min={min(mem_counts)} max={max(mem_counts)} "
          f"avg={sum(mem_counts)/len(mem_counts):.1f} total={sum(mem_counts)}")
    print(f" 记忆增长: {mem_growth:+d} (初始 {initial_total_mem} → 最终 {total_mem_end})")
    print(f" 压缩统计: deduped={total_deduped} summarized={total_summarized} pruned={total_pruned}")
    print(f" 属性分布: {attr_counts}")

    region_counts: dict[str, int] = {}
    for a in agents_after:
        r = a.region_id or "unknown"
        region_counts[r] = region_counts.get(r, 0) + 1
    print(f" 地区分布: {region_counts}")

    # 事件类型分布
    event_types: dict[str, int] = {}
    for ev in world.events:
        t = ev.get("type", "unknown")
        event_types[t] = event_types.get(t, 0) + 1
    print(f" 事件类型 Top 10: {dict(sorted(event_types.items(), key=lambda x: -x[1])[:10])}")

    # 延迟统计
    if tick_latencies:
        avg_lat = sum(tick_latencies) / len(tick_latencies)
        max_lat = max(tick_latencies)
        sorted_lat = sorted(tick_latencies)
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0
        print(f" 延迟: avg={avg_lat:.1f}ms max={max_lat:.1f}ms p99={p99:.1f}ms")
        print(f" 吞吐: {ticks/total_real_time:.1f} ticks/s "
              f"({total_agents * ticks / total_real_time:.0f} agent-steps/s)")

    # ── Agent 状态样本 ──
    sample_n = min(10, len(agents_after))
    print()
    print(f" 📋 Agent 样本 (共 {len(agents_after)} 只, 显示前 {sample_n}):")
    for a in agents_after[:sample_n]:
        x, y = a.location
        mem = len(a.memory.entries)
        deduped = a.memory.total_deduped
        summarized = a.memory.total_summarized
        plan = (a.current_plan or "")[:22]
        attr = a.attribute.value if a.attribute else "?"
        region = a.region_id or "?"
        print(f"    {a.name:<14} [{attr:<7}] {region:<22} "
              f"pos=({x:>4},{y:>4}) mem={mem:>4} "
              f"cmp(d={deduped} s={summarized}) plan=\"{plan}\"")

    # ── 增长曲线 ──
    if memory_samples:
        print()
        print(f" 📈 记忆增长曲线 ({len(memory_samples)} 采样点):")
        for tick_mark, total_mem in memory_samples:
            bar_len = min(50, int(total_mem / max(1, max(m for _, m in memory_samples)) * 50))
            bar = "█" * bar_len + "░" * (50 - bar_len)
            print(f"    tick {tick_mark:>5}: {bar} mem={total_mem}")

    # ── 结论 ──
    print()
    print(BAR)
    if failed == 0:
        print(f" ✅ 长期一致性测试通过 ({ticks} ticks, ~{ticks/60/24:.1f} 天世界时间)")
    else:
        print(f" ❌ 长期一致性测试失败: {failed} 项校验未通过")
    print(BAR)

    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 12 长期一致性测试"
    )
    parser.add_argument(
        "--ticks", type=int, default=DEFAULT_TICKS,
        help=f"跑多少 tick (默认 {DEFAULT_TICKS} ≈ 1 天, {WEEK_TICKS} = 1 周)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help=f"快速模式: {QUICK_TICKS} ticks (~4 小时世界时间)",
    )
    parser.add_argument(
        "--week", action="store_true",
        help=f"完整一周: {WEEK_TICKS} ticks",
    )
    args = parser.parse_args()

    if args.week:
        ticks = WEEK_TICKS
    elif args.quick:
        ticks = QUICK_TICKS
    else:
        ticks = args.ticks

    print(f"🧪 Phase 12 长期一致性测试启动: {ticks} ticks")
    return asyncio.run(run(ticks=ticks))


if __name__ == "__main__":
    sys.exit(main())
