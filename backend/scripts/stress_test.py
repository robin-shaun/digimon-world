#!/usr/bin/env python3
"""
Phase 11 ⑧ Agent 100+ 压力测试
================================

目标: 验证系统在 100+ 只数码兽同时运行时的性能与一致性。

跑法(零网络依赖):

    cd backend
    source .venv/bin/activate
    python scripts/stress_test.py              # 默认 100 agents × 20 ticks
    python scripts/stress_test.py --agents 200 # 200 agents
    python scripts/stress_test.py --ticks 30   # 30 ticks

报告指标:
- 每 tick 平均/最大/P99 延迟 (ms)
- 内存估算 (每 agent 平均记忆条目数)
- 世界事件总量 / 每秒事件产出
- 一致性校验 (位置/region/记忆存在性)
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

from digimon_world.agents.digimon_agent import DigimonAgent, DigimonAttribute
from digimon_world.agents.dialogue import Dialogue
from digimon_world.llm.client import (
    FakeLlmClient,
    LlmModel,
    get_client,
    set_client,
)
from digimon_world.world import WorldClock, WorldScheduler
from digimon_world.world.world_state import WorldState

DEFAULT_AGENTS = 100
DEFAULT_TICKS = 20

BAR = "=" * 65
SUB = "-" * 65

# ── FakeLlmClient for stress test ──────────────────────────────────


def _build_stress_fake_client() -> FakeLlmClient:
    """构造 100-agent 可用的 FakeLlmClient，回复简单避免大量内存。"""
    fake = FakeLlmClient()

    # Dialogue lines (minimal)
    for i in range(100):
        fake.set_reply(
            LlmModel.HAIKU,
            contains=f"dlg_idx={i}",
            reply=f"你好!我是数码兽#{i}。",
        )
    fake.set_reply(LlmModel.HAIKU, contains="只输出这句台词", reply="你好!")
    fake.set_reply(LlmModel.HAIKU, reply="...")

    # Planner replies
    plans = ["闲逛", "巡逻", "探索", "休息", "找食物", "向山顶进发", "回巢穴"]
    for i, p in enumerate(plans):
        fake.set_reply(
            LlmModel.HAIKU,
            contains=f"plan_idx={i}",
            reply=p,
        )
    fake.set_reply(LlmModel.HAIKU, contains="plan", reply="闲逛")
    fake.set_reply(LlmModel.HAIKU, reply="闲逛")

    # Reflector replies
    for i in range(100):
        fake.set_reply(
            LlmModel.OPUS,
            contains=f"refl_idx={i}",
            reply=f"一切都正常 #{i}。",
        )
    fake.set_reply(LlmModel.OPUS, contains="reflect", reply="一切正常。")
    fake.set_reply(LlmModel.OPUS, reply="一切正常。")

    return fake


# ── Agent 种子生成 ─────────────────────────────────────────────────

_SPECIES_POOL = [
    "agumon", "gabumon", "biyomon", "tentomon", "palmon",
    "gomamon", "patamon", "plotmon", "elecmon", "tsunomon",
    "hagurumon", "guardromon", "clockmon", "tankmon", "kokuwamon",
    "renamon", "impmon", "dorumon", "picodevimon", "blackgabumon",
    "tailmon", "devimon", "devidramon", "vamdemon", "fantomon",
    "bakemon", "andromon", "wizarmon", "leomon", "gaomon",
    "lalamon", "falcomon", "kudamon", "dracmon", "dracomon",
    "veemon", "wormmon", "hawkmon", "armadillomon", "terriermon",
    "lopmon", "guilmon", "renamonx", "dobermon", "knightmon",
    "beelzebumon", "omnisamon", "alphamon", "jijimon", "babamon",
]
_ATTRIBUTES = ["vaccine", "data", "virus", "free"]
_REGIONS = ["file_island", "infinity_mountain"]
_PLANS = [
    "在沙滩附近闲逛", "安静地观察周围", "从空中巡视", "在树林里找食物",
    "晒太阳光合作用", "在海边玩水", "在空中飞行", "在草地上玩耍",
    "在发电站附近巡逻", "在玩具城附近探索", "在齿轮草原计算数据",
    "在工厂地带巡逻警戒", "在龙眼湖附近做实验", "在迷乱森林修炼忍术",
    "在无人商店附近恶作剧", "在冰冻地带适应寒冷", "在暗黑洞窟附近潜伏",
    "在无限山顶散布黑暗力量", "在无限山深处沉睡", "在暗处策划阴谋",
    "在无限山游荡收割灵魂", "在无限山修炼正义之拳",
]


def _generate_agent_seeds(count: int) -> list[dict]:
    """程序化生成 N 只数码兽种子，属性/区域均匀分布。"""
    import random
    rng = random.Random(42)  # 固定种子，可复现
    seeds = []
    for i in range(count):
        attr = rng.choice(_ATTRIBUTES)
        region = rng.choice(_REGIONS)
        # 位置避开其他 agent 的常见聚集区
        if region == "file_island":
            x = rng.randint(50, 1150)
            y = rng.randint(50, 750)
        else:
            x = rng.randint(150, 750)
            y = rng.randint(50, 550)
        species = _SPECIES_POOL[i % len(_SPECIES_POOL)]
        plan = rng.choice(_PLANS)
        seeds.append({
            "name": f"StressAgent_{i:04d}",
            "species": species,
            "attribute": attr,
            "region": region,
            "pos": (x, y),
            "plan": plan,
        })
    return seeds


_ATTR_MAP = {
    "vaccine": DigimonAttribute.VACCINE,
    "data": DigimonAttribute.DATA,
    "virus": DigimonAttribute.VIRUS,
    "free": DigimonAttribute.FREE,
}


def _spawn_from_seed(world: WorldState, seed: dict) -> DigimonAgent:
    agent = DigimonAgent(
        name=seed["name"],
        species=seed["species"],
        attribute=_ATTR_MAP.get(seed["attribute"], DigimonAttribute.FREE),
        region_id=seed["region"],
        location=seed["pos"],
        current_plan=seed["plan"],
    )
    import random as _random
    agent.latent_desire = ""
    agent.desire_strength = 0.0
    return agent


# ── 主流程 ─────────────────────────────────────────────────────────


async def run(agent_count: int, ticks: int) -> int:
    """运行压力测试。返回 0=PASS, 1=FAIL。"""

    print(BAR)
    print(f" Phase 11 ⑧ Agent 100+ 压力测试")
    print(f" agents={agent_count}  ticks={ticks}")
    print(BAR)

    # 注入 FakeLlmClient
    set_client(_build_stress_fake_client())

    # 构建世界
    world = WorldState(world_id="stress_test")
    seeds = _generate_agent_seeds(agent_count)
    for seed in seeds:
        agent = _spawn_from_seed(world, seed)
        world.spawn(agent)

    all_agents = world.all()
    print(f" ✓ {len(all_agents)} agents spawned")
    print(f"   seed file_island={sum(1 for s in seeds if s['region']=='file_island')}  "
          f"infinity_mountain={sum(1 for s in seeds if s['region']=='infinity_mountain')}")
    print(SUB)

    clock = WorldClock(real_to_world_ratio=60)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)

    # ── 跑 ticks，记录延迟 ──
    tick_latencies: list[float] = []
    progress_interval = max(1, ticks // 5)

    for i in range(ticks):
        t0 = time.perf_counter()
        await scheduler.tick_once(real_seconds=1.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        tick_latencies.append(elapsed_ms)

        if (i + 1) % progress_interval == 0 or i == 0:
            print(
                f"  [tick {i + 1:>3}/{ticks}] "
                f"latency={elapsed_ms:>7.1f}ms  "
                f"world_time={clock.format_clock()}  "
                f"events={len(world.events)}  "
                f"scheduler_ticks={scheduler.tick_count}"
            )

    print(SUB)

    # ── 统计延迟 ──
    avg_lat = sum(tick_latencies) / len(tick_latencies) if tick_latencies else 0
    max_lat = max(tick_latencies) if tick_latencies else 0
    sorted_lat = sorted(tick_latencies)
    p99_idx = int(len(sorted_lat) * 0.99)
    p99_lat = sorted_lat[p99_idx] if p99_idx < len(sorted_lat) else sorted_lat[-1]

    print(f" 📊 延迟统计 (每 tick):")
    print(f"    avg={avg_lat:.1f}ms  max={max_lat:.1f}ms  p99={p99_lat:.1f}ms")
    print(f"    total_time={sum(tick_latencies):.0f}ms  (real elapsed)")

    # ── 校验 ──
    results: list[tuple[str, bool, str]] = []

    # 1. Agent 数量不变
    agents_after = world.all()
    count_ok = len(agents_after) == agent_count
    results.append((
        "1. agent count stable",
        count_ok,
        f"expected={agent_count} got={len(agents_after)}",
    ))

    # 2. 所有 agent 在画布内
    canvas_w, canvas_h = 1200, 800
    all_bounds_ok = True
    oob_count = 0
    for a in agents_after:
        x, y = a.location
        if not (0 <= x <= canvas_w and 0 <= y <= canvas_h):
            oob_count += 1
            all_bounds_ok = False
    results.append((
        "2. all agents in canvas",
        all_bounds_ok,
        f"OOB={oob_count}/{len(agents_after)}",
    ))

    # 3. 所有 agent 有 region
    no_region = sum(1 for a in agents_after if not a.region_id)
    region_ok = no_region == 0
    results.append((
        "3. all agents have region",
        region_ok,
        f"missing={no_region}/{len(agents_after)}",
    ))

    # 4. Scheduler tick count
    tick_ok = scheduler.tick_count == ticks
    results.append((
        "4. scheduler tick_count",
        tick_ok,
        f"got={scheduler.tick_count} expected={ticks}",
    ))

    # 5. 至少产生一些事件
    event_count = len(world.events)
    events_ok = event_count >= ticks  # 每 tick 至少 1 个事件
    results.append((
        "5. events >= ticks",
        events_ok,
        f"events={event_count} (expected >= {ticks})",
    ))

    # 6. 记忆分布
    mem_counts = [len(a.memory.entries) for a in agents_after]
    avg_mem = sum(mem_counts) / len(mem_counts) if mem_counts else 0
    max_mem = max(mem_counts) if mem_counts else 0
    min_mem = min(mem_counts) if mem_counts else 0
    zero_mem = sum(1 for m in mem_counts if m == 0)
    mem_ok = zero_mem == 0 and max_mem < 500
    results.append((
        "6. memory non-zero & bounded",
        mem_ok,
        f"min={min_mem} avg={avg_mem:.1f} max={max_mem} zero={zero_mem}",
    ))

    # 7. 时钟推进
    elapsed_ok = clock.elapsed_minutes >= ticks - 2
    results.append((
        "7. clock elapsed",
        elapsed_ok,
        f"elapsed={clock.elapsed_minutes}min (expected >= {ticks - 2})",
    ))

    # 8. 属性分布至少覆盖 4 种
    attr_counts: dict[str, int] = {}
    for a in agents_after:
        key = a.attribute.value if a.attribute else "?"
        attr_counts[key] = attr_counts.get(key, 0) + 1
    attr_ok = len(attr_counts) >= 3  # 至少 3 种不同属性
    results.append((
        "8. attribute diversity",
        attr_ok,
        f"types={len(attr_counts)} distribution={attr_counts}",
    ))

    # ── 打印校验表 ──
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:<35}  {detail}")
    print(SUB)
    print(f" 校验汇总: {passed} PASS / {failed} FAIL")

    # ── Agent 状态样本 ──
    sample_n = min(10, len(agents_after))
    print()
    print(f" 📋 Agent 样本 (共 {len(agents_after)} 只, 显示前 {sample_n}):")
    for a in agents_after[:sample_n]:
        x, y = a.location
        mem = len(a.memory.entries)
        plan = (a.current_plan or "")[:18]
        attr = a.attribute.value if a.attribute else "?"
        print(f"    {a.name:<20} [{attr:<7}] pos=({x:>4},{y:>4}) mem={mem:>3} plan=\"{plan}\"")

    plan_samples = [a.current_plan or "" for a in agents_after]
    unique_plans = set(plan_samples)
    print(f"\n   unique plans: {len(unique_plans)} / {len(agents_after)}")

    # ── 性能结论 ──
    print()
    print(BAR)
    print(f" ✅ 压力测试完成")
    print(f"    agents:     {agent_count}")
    print(f"    ticks:      {ticks}")
    print(f"    avg_lat:    {avg_lat:.1f}ms/tick")
    print(f"    events:     {event_count}")
    print(f"    events/sec: {event_count / (sum(tick_latencies) / 1000):.0f}")
    print(f"    total_mem:  {sum(mem_counts)} entries  (avg {avg_mem:.1f}/agent)")
    print(f"    pass_rate:  {passed}/{passed + failed}")
    print(BAR)

    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 11 Agent 100+ 压力测试")
    parser.add_argument(
        "--agents", type=int, default=DEFAULT_AGENTS,
        help=f"生成的数码兽数量 (default: {DEFAULT_AGENTS})",
    )
    parser.add_argument(
        "--ticks", type=int, default=DEFAULT_TICKS,
        help=f"跑多少 tick (default: {DEFAULT_TICKS})",
    )
    args = parser.parse_args()
    return asyncio.run(run(agent_count=args.agents, ticks=args.ticks))


if __name__ == "__main__":
    sys.exit(main())
