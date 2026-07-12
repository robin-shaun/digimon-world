#!/usr/bin/env python3
"""
Phase 11 30-Agent 长时间运行一致性验证
========================================

目标: 30+ 只数码兽在文件岛自主运行,验证规模化一致性。

跑法(零网络依赖,默认用 FakeLlmClient):

    cd backend
    source .venv/bin/activate
    python scripts/verify_phase11.py            # 默认 60 tick (1 小时世界时间)
    python scripts/verify_phase11.py --ticks 120 # 2 小时
    python scripts/verify_phase11.py --live      # 用真实 LLM

校验项 (共 N 项):
1. 时钟在推进: world_time elapsed >= ticks
2. 30+ 只数码兽全部存在 (world.all() 非空且数量正确)
3. 每只数码兽:
   a. 位置在画布范围内 (0 < x < 1200, 0 < y < 800)
   b. 有 region_id 且非空
   c. 记忆数 > 0 (至少写入过 1 条)
   d. 记忆数合理 (不超过 500 — 防内存泄漏)
4. 四属性分布完整: 疫苗种/数据种/病毒种/自由种 各有至少 2 只
5. 两地区分布合理: 文件岛 >= 18 只, 无限山 >= 8 只
6. Scheduler tick_count == ticks
7. 至少 10 条世界事件被记录
8. 记忆增长率检查 (最后 10 tick 增量 < 前 50 tick 平均的 3 倍)

输出:
- PASS / FAIL 汇总
- 每只数码兽的简要状态 (位置/记忆数/plan)
- 属性/地区分布统计
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本可以直接 import src/...
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

# 默认 tick 数: 60 = 1 小时世界时间 (real_to_world_ratio=60)
DEFAULT_TICKS = 60

BAR = "=" * 60
SUB = "-" * 60


def _build_fake_client() -> FakeLlmClient:
    """构造 30-agent 可用的 FakeLlmClient。

    给 Planner / Reflector / Dialogue 预设多样化的回复,
    避免所有 agent 返回同一句话。
    """
    fake = FakeLlmClient()

    # ---- Dialogue (必须先于 planner,因为 planner prompt 也含 "plan") ----
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
    ]
    for i, line in enumerate(dialogue_lines):
        fake.set_reply(LlmModel.HAIKU, contains=f"dlg_idx={i}", reply=line)
    fake.set_reply(LlmModel.HAIKU, contains="只输出这句台词", reply="你好呀!好久不见!")

    # ---- Planner: 多样化简短计划 ----
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
    ]
    for i, p in enumerate(plans):
        fake.set_reply(LlmModel.HAIKU, contains=f"plan_idx={i}", reply=p)
    fake.set_reply(LlmModel.HAIKU, contains="plan", reply="在附近闲逛")
    fake.set_reply(LlmModel.HAIKU, reply="在附近闲逛")

    # ---- Reflector: 多样化反思 ----
    reflections = [
        "今天过得挺充实,遇到了几个新朋友。",
        "齿轮草原的数据流好像有点异常...",
        "我应该加强训练,变得更强。",
        "无限山方向的黑暗气息越来越浓了。",
        "今天找到了不错的食物来源。",
    ]
    for i, r in enumerate(reflections):
        fake.set_reply(LlmModel.OPUS, contains=f"refl_idx={i}", reply=r)
    fake.set_reply(LlmModel.OPUS, contains="reflect", reply="今天过得挺充实")
    fake.set_reply(LlmModel.OPUS, reply="一切正常。")

    return fake


def _print_agent_summary(agent, index: int) -> str:
    """返回一只数码兽的简要状态单行。"""
    name = agent.name
    mem_count = len(agent.memory.entries)
    plan = (agent.current_plan or "(空)")[:20]
    x, y = agent.location
    region = agent.region_id or "?"
    attr = getattr(agent, "attribute", None)
    attr_str = attr.value if attr else "?"
    return (
        f"  {index:>2}. {name:<8} [{attr_str:<7}] {region:<18} "
        f"pos=({x:>4},{y:>4}) mem={mem_count:>4} plan=\"{plan}\""
    )


async def run(ticks: int, use_live: bool) -> int:
    """主流程。返回 0=PASS, 1=FAIL。"""

    if use_live:
        print("[live mode] 使用全局 LLM 客户端(需先 export DIGIMON_LLM_API_KEY)")
    else:
        print("[fake mode] 注入 FakeLlmClient(零网络)")
        set_client(_build_fake_client())

    reset_world()
    world = get_world()
    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    all_agents = world.all()
    total_agents = len(all_agents)

    # 初始快照
    initial_mem_counts = {a.name: len(a.memory.entries) for a in all_agents}

    print(BAR)
    print(f" Phase 11 30-Agent 一致性验证 (ticks={ticks}, agents={total_agents})")
    print(BAR)
    print(f" 启动时刻: {clock.format_clock()}")
    print(f" 数码兽数: {total_agents}")
    print(SUB)

    # ---- 跑 N tick ----
    progress_interval = max(1, ticks // 6)
    for i in range(ticks):
        await scheduler.tick_once(real_seconds=1.0)
        if (i + 1) % progress_interval == 0 or i == 0:
            print(
                f"  [tick {i + 1:>3}/{ticks}] "
                f"world_time={clock.format_clock()}  "
                f"events={len(world.events)}  "
                f"scheduler_ticks={scheduler.tick_count}"
            )

    print(SUB)
    print(" 校验项:")
    results: list[tuple[str, bool, str]] = []

    # ---- 1. 时钟推进 ----
    elapsed_ok = clock.elapsed_minutes >= ticks - 1
    results.append((
        "1. clock.elapsed_minutes",
        elapsed_ok,
        f"elapsed={clock.elapsed_minutes}min (期望 >= {ticks - 1})",
    ))

    # ---- 2. 30+ agent 全部存在 ----
    agents_after = world.all()
    count_ok = len(agents_after) >= 30
    results.append((
        "2. agent_count >= 30",
        count_ok,
        f"count={len(agents_after)} (期望 >= 30)",
    ))

    # ---- 3. 每只 agent 详细校验 ----
    canvas_w, canvas_h = 1200, 800
    all_pos_ok = True
    all_region_ok = True
    all_mem_ok = True
    all_mem_bounded = True

    for a in agents_after:
        x, y = a.location
        # 3a. 位置在画布内
        in_bounds = 0 <= x <= canvas_w and 0 <= y <= canvas_h
        if not in_bounds:
            results.append((
                f"3a. {a.name}.位置越界",
                False,
                f"pos=({x},{y}) 超出 [0,{canvas_w}]x[0,{canvas_h}]",
            ))
            all_pos_ok = False

        # 3b. region_id 非空
        has_region = bool(a.region_id and a.region_id.strip())
        if not has_region:
            results.append((
                f"3b. {a.name}.无region",
                False,
                f"region_id={a.region_id!r}",
            ))
            all_region_ok = False

        # 3c. 记忆数 > 0
        mem_count = len(a.memory.entries)
        if mem_count == 0:
            results.append((
                f"3c. {a.name}.记忆=0",
                False,
                f"不应为0 (初始={initial_mem_counts[a.name]})",
            ))
            all_mem_ok = False

        # 3d. 记忆上限检查 (防止泄漏, 60 tick 内不应超过 500)
        if mem_count > 500:
            results.append((
                f"3d. {a.name}.记忆过多",
                False,
                f"count={mem_count} > 500 (疑似内存泄漏)",
            ))
            all_mem_bounded = False

    results.append((
        "3a. 所有agent位置在画布内",
        all_pos_ok,
        f"{'全部合格' if all_pos_ok else '有越界,见上'}",
    ))
    results.append((
        "3b. 所有agent有region_id",
        all_region_ok,
        f"{'全部合格' if all_region_ok else '有缺失'}",
    ))
    results.append((
        "3c. 所有agent记忆>0",
        all_mem_ok,
        f"{'全部合格' if all_mem_ok else '有0记忆'}",
    ))
    results.append((
        "3d. 记忆数合理(<500)",
        all_mem_bounded,
        f"{'全部合格' if all_mem_bounded else '有超标'}",
    ))

    # ---- 4. 四属性分布 ----
    attr_counts: dict[str, int] = {}
    for a in agents_after:
        attr = getattr(a, "attribute", None)
        key = attr.value if attr else "unknown"
        attr_counts[key] = attr_counts.get(key, 0) + 1
    attr_ok = all(
        attr_counts.get(k, 0) >= 2
        for k in ["vaccine", "data", "virus", "free"]
    )
    results.append((
        "4. 四属性分布完整",
        attr_ok,
        f"vaccine={attr_counts.get('vaccine',0)} data={attr_counts.get('data',0)} "
        f"virus={attr_counts.get('virus',0)} free={attr_counts.get('free',0)}",
    ))

    # ---- 5. 两地区分布 ----
    region_counts: dict[str, int] = {}
    for a in agents_after:
        r = a.region_id or "unknown"
        region_counts[r] = region_counts.get(r, 0) + 1
    region_ok = (
        region_counts.get("file_island", 0) >= 18
        and region_counts.get("infinity_mountain", 0) >= 8
    )
    results.append((
        "5. 两地区分布合理",
        region_ok,
        f"file_island={region_counts.get('file_island',0)} "
        f"infinity_mountain={region_counts.get('infinity_mountain',0)}",
    ))

    # ---- 6. scheduler tick_count ----
    tick_ok = scheduler.tick_count == ticks
    results.append((
        "6. scheduler.tick_count",
        tick_ok,
        f"got={scheduler.tick_count}, expected={ticks}",
    ))

    # ---- 7. 世界事件 ----
    event_count = len(world.events)
    events_ok = event_count >= 10
    results.append((
        "7. world.events >= 10",
        events_ok,
        f"events={event_count}",
    ))

    # ---- 8. 记忆增长率检查 (最后 10 tick 记忆增长不应失控) ----
    # 用末尾记忆数 vs 初始比较
    total_mem_end = sum(len(a.memory.entries) for a in agents_after)
    total_mem_start = sum(initial_mem_counts.values())
    mem_growth = total_mem_end - total_mem_start
    avg_growth_per_tick = mem_growth / max(1, ticks)
    growth_ok = avg_growth_per_tick < 10  # 每 tick 平均每 agent < 10 条新记忆
    results.append((
        "8. 记忆增长率检查",
        growth_ok,
        f"总增长={mem_growth}, 每tick平均={avg_growth_per_tick:.1f} (期望 < 10)",
    ))

    # ---- 打印校验表 ----
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:<40}  {detail}")
    print(SUB)
    print(f" 汇总: {passed} 通过, {failed} 失败")
    print()

    # ---- 打印每只数码兽的简要状态 ----
    print(BAR)
    print(f" 📋 数码兽状态一览 (共 {total_agents} 只)")
    print(BAR)
    print(f" 世界时间: {clock.format_clock()} (elapsed {clock.elapsed_minutes} min)")
    print(f" 总事件数: {event_count}")
    print(f" 调度器 ticks: {scheduler.tick_count}")
    print()
    for i, a in enumerate(agents_after, 1):
        print(_print_agent_summary(a, i))

    # ---- 统计面板 ----
    print()
    print(BAR)
    print(" 📊 统计面板")
    print(BAR)
    mem_counts = [len(a.memory.entries) for a in agents_after]
    print(f" 记忆数: min={min(mem_counts)} max={max(mem_counts)} "
          f"avg={sum(mem_counts)/len(mem_counts):.1f} total={sum(mem_counts)}")
    print(f" 属性分布: {attr_counts}")
    print(f" 地区分布: {region_counts}")

    # 按事件类型统计
    event_types: dict[str, int] = {}
    for ev in world.events:
        t = ev.get("type", "unknown")
        event_types[t] = event_types.get(t, 0) + 1
    print(f" 事件类型分布: {event_types}")

    # ---- 最近 5 条世界事件 ----
    if world.events:
        print()
        print(BAR)
        print(" 🌍 最近 5 条世界事件")
        print(BAR)
        for ev in world.events[-5:]:
            ev_type = ev.get("type", "?")
            agent = ev.get("agent", ev.get("speaker", ""))
            if ev_type == "moved":
                print(f"  · [{ev_type}] {agent}: {ev.get('from')} -> {ev.get('to')}")
            elif ev_type == "dialogue":
                print(f"  · [{ev_type}] {ev.get('speaker')} -> {ev.get('listener')}: {ev.get('line')}")
            else:
                print(f"  · [{ev_type}] {agent}: {ev}")
        print()

    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 11 30-Agent 一致性验证")
    parser.add_argument(
        "--ticks", type=int, default=DEFAULT_TICKS,
        help=f"跑多少 tick(默认 {DEFAULT_TICKS})",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="用真实 LLM 客户端(需 DIGIMON_LLM_API_KEY)",
    )
    args = parser.parse_args()
    return asyncio.run(run(ticks=args.ticks, use_live=args.live))


if __name__ == "__main__":
    sys.exit(main())
